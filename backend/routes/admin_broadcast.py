"""Admin broadcast endpoints — LEGAL notices + SECURITY incidents.

Both broadcasts share the same safety architecture:
  1. DRY-RUN FIRST: `dry_run=True` returns recipient count WITHOUT sending
     so the admin can confirm the audience size before committing.
  2. TYPE-SEND GATE: the real send requires `confirm_phrase == "SEND"`
     so muscle-memory clicks cannot push out an irreversible broadcast
     going to the entire user base.
  3. RATE LIMIT: max 1 full-audience broadcast per 5 minutes per admin
     (protects against double-send mistakes AND a compromised admin
     account being weaponized to phish users via our own channel).
  4. AUDIT LOG: every real send is persisted to a dedicated collection
     with the full payload + sent/failed counts, AND auto-logged to the
     Compliance Digest Hub so it surfaces in the audit trail reviewers
     already watch.
  5. REGULATORY FIT: the SECURITY-incident variant also fans out a
     web + Expo push via `send_push_notification` so affected users
     see "reset your password" instantly — email in-box latency is a
     liability during an active breach.

Endpoints (all require admin):
  POST /api/admin/legal-notice/broadcast       — ToS / Privacy Policy update
  GET  /api/admin/legal-notice/broadcasts      — audit feed
  POST /api/admin/security-incident/broadcast  — breach / cyberattack alert
  GET  /api/admin/security-incident/broadcasts — audit feed
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator

from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


LEGAL_COL = "legal_notice_broadcasts"
LEGAL_SCHEDULE_COL = "legal_notice_schedules"
LEGAL_SCHEDULE_AUDIT_COL = "legal_notice_schedule_audit"
LEGAL_DELIVERY_COL = "legal_notice_delivery_events"
SEC_COL = "security_incident_broadcasts"
RATE_LIMIT_SECONDS = 300  # 5 minutes between full-audience broadcasts per admin
CONFIRM_PHRASE = "SEND"


# ─────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_utc(raw: str) -> datetime:
    """Parse ISO datetime into timezone-aware UTC datetime."""
    try:
        dt = datetime.fromisoformat(str(raw or "").replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ISO datetime format")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _rate_limit_or_raise(actor_email: str, collection_name: str) -> None:
    """Raise 429 if this admin sent another broadcast of the same kind in
    the last RATE_LIMIT_SECONDS window. Dry-runs do NOT count — only real
    sends (recorded in the audit collection) enforce the limit."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=RATE_LIMIT_SECONDS)).isoformat()
    recent = await db[collection_name].find_one(
        {"broadcast_by": actor_email, "sent_at": {"$gte": cutoff}, "dry_run": {"$ne": True}},
        {"_id": 0, "sent_at": 1},
        sort=[("sent_at", -1)],
    )
    if recent:
        retry_iso = recent["sent_at"]
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limited: a broadcast of this kind was sent in the last "
                f"{RATE_LIMIT_SECONDS // 60} minutes (at {retry_iso}). Wait before "
                f"sending another. This prevents accidental double-sends."
            ),
        )


def _assert_confirm_phrase(confirm_phrase: Optional[str]) -> None:
    """Type-SEND gate. The real send requires the admin to have typed
    exactly "SEND" in the confirmation input."""
    if (confirm_phrase or "").strip() != CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=(
                f'Confirmation phrase required. Type "{CONFIRM_PHRASE}" exactly '
                f"to confirm a real broadcast, or set dry_run=true to preview "
                f"the recipient count without sending."
            ),
        )


async def _target_users(audience: str, user_ids: Optional[list[str]]) -> list[dict[str, Any]]:
    """Resolve the recipient list. `affected_only` requires an explicit
    user_ids list so the admin never accidentally targets the whole base
    when they meant a subset."""
    q: dict[str, Any] = {
        "access_locked": {"$ne": True},
        "email": {"$exists": True, "$ne": ""},
    }
    if audience == "affected_only":
        if not user_ids:
            raise HTTPException(
                status_code=400,
                detail="audience=affected_only requires a non-empty user_ids list.",
            )
        q["user_id"] = {"$in": list(user_ids)}
    return await db.users.find(q, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(100000)


async def _log_digest_entry_safe(kind: str, subject: str, summary: str, recipient_count: int, sent_ok: int, sent_failed: int, actor: str) -> None:
    """Fire-and-forget: write an entry to the Compliance Digest Hub so the
    broadcast shows up in the same audit feed reviewers already watch.
    Never raises — audit is advisory, not blocking. We intentionally pass
    recipients=[] to avoid leaking user emails into the digest record;
    the recipient_count travels in the payload sub-dict and the dedicated
    per-kind broadcast collections hold the real audit trail."""
    try:
        from routes.compliance_digest_hub import log_digest_entry  # type: ignore
        await log_digest_entry(
            kind=kind,
            subject=subject,
            summary=summary,
            recipients=[],
            sent_ok=sent_ok,
            sent_failed=sent_failed,
            payload={"recipient_count": recipient_count, "actor": actor},
            trigger=f"admin_broadcast:{actor}",
        )
    except Exception as e:
        logger.debug(f"[admin_broadcast] compliance digest logging skipped: {e}")


# ─────────────────────────────────────────────────────────────────────────
# 1) Legal Notice Broadcast (ToS / Privacy Policy update)
# ─────────────────────────────────────────────────────────────────────────


class LegalNoticeBody(BaseModel):
    policy_type: str = Field(..., min_length=2, max_length=120)
    effective_date: str = Field(..., min_length=2, max_length=80)
    summary_of_changes: str = Field(..., min_length=10, max_length=2000)
    review_url: Optional[str] = Field(None, max_length=500)
    audience: Literal["all_users", "affected_only"] = "all_users"
    user_ids: Optional[list[str]] = None
    dry_run: bool = True
    confirm_phrase: Optional[str] = None


class LegalScheduleCreateBody(BaseModel):
    policy_type: Literal["Terms of Service", "Privacy Policy", "Cookie Policy"]
    effective_date: str
    summary_of_changes: str = Field(min_length=10, max_length=800)
    review_url: Optional[str] = Field(default="", max_length=300)
    audience: Literal["all_users", "affected_only"] = "all_users"
    user_ids: list[str] = Field(default_factory=list)
    scheduled_send_at: str
    timezone: str = Field(default="UTC", max_length=50)
    notification_send_at: Optional[str] = None
    approval_required: bool = True


class LegalScheduleUpdateBody(BaseModel):
    effective_date: Optional[str] = None
    summary_of_changes: Optional[str] = Field(default=None, min_length=10, max_length=800)
    review_url: Optional[str] = Field(default=None, max_length=300)
    audience: Optional[Literal["all_users", "affected_only"]] = None
    user_ids: Optional[list[str]] = None
    scheduled_send_at: Optional[str] = None
    timezone: Optional[str] = Field(default=None, max_length=50)
    notification_send_at: Optional[str] = None
    approval_required: Optional[bool] = None


class LegalScheduleDecisionBody(BaseModel):
    note: Optional[str] = Field(default="", max_length=600)


class LegalSuggestionFeedbackBody(BaseModel):
    schedule_id: Optional[str] = None
    policy_type: Literal["Terms of Service", "Privacy Policy", "Cookie Policy"]
    intent: Literal["draft", "improve_tone", "shorten", "expand"]
    style_preset: Optional[Literal["formal", "regulatory", "plain-language"]] = None
    decision: Literal["accepted", "rejected"]
    source: Optional[str] = Field(default="", max_length=120)
    confidence: Optional[float] = None
    summary_length: Optional[int] = None
    note: Optional[str] = Field(default="", max_length=400)


async def _append_legal_schedule_audit(schedule_id: str, action: str, actor: str, details: Optional[dict] = None):
    payload = {
        "event_id": f"ls_evt_{uuid.uuid4().hex[:12]}",
        "schedule_id": schedule_id,
        "action": action,
        "actor": actor,
        "details": details or {},
        "created_at": _now_iso(),
    }
    await db[LEGAL_SCHEDULE_AUDIT_COL].insert_one(payload)
    safe_payload = dict(payload)
    safe_payload.pop("_id", None)
    return safe_payload


def _serialize_schedule(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    data = dict(doc)
    data.pop("_id", None)
    return data


async def _send_legal_notice_now(
    *,
    actor: str,
    body: LegalNoticeBody,
    trigger: str,
    schedule_id: Optional[str] = None,
    enforce_rate_limit: bool = True,
) -> dict:
    users = await _target_users(body.audience, body.user_ids)
    recipient_count = len(users)
    if recipient_count == 0:
        raise HTTPException(status_code=400, detail="No target users")

    if enforce_rate_limit:
        await _rate_limit_or_raise(actor, LEGAL_COL)

    from utils.email_service import send_catalog_template, is_email_configured
    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service is not configured.")

    summary = body.summary_of_changes.strip()
    sent, failed = 0, 0
    errors: list[dict[str, Any]] = []
    broadcast_id = f"legal_{uuid.uuid4().hex[:12]}"
    sent_at = _now_iso()
    delivery_docs: list[dict] = []

    for u in users:
        try:
            result = await send_catalog_template(
                recipient_email=u["email"],
                template_key="terms_policy_update",
                recipient_name=u.get("name", ""),
                user_name=u.get("name") or "there",
                policy_type=body.policy_type,
                effective_date=body.effective_date,
                summary_of_changes=summary,
                review_url=body.review_url or "",
                dedupe_key=f"legal-notice-{body.policy_type}-{body.effective_date}-{u['user_id']}",
                expected_user_id=u["user_id"],
                enforce_verified_primary=True,
            )
            if result.get("success"):
                sent += 1
                message_id = str(result.get("message_id") or "").strip()
                if message_id:
                    delivery_docs.append({
                        "delivery_id": f"ldev_{uuid.uuid4().hex[:12]}",
                        "broadcast_id": broadcast_id,
                        "schedule_id": schedule_id,
                        "policy_type": body.policy_type,
                        "email_id": message_id,
                        "recipient": u["email"],
                        "user_id": u["user_id"],
                        "sent_at": sent_at,
                    })
            else:
                failed += 1
                errors.append({"email": u.get("email"), "error": result.get("error", "send_failed")})
        except Exception as e:
            logger.warning(f"[legal-notice] send failed for {u.get('email')}: {e}")
            failed += 1
            errors.append({"email": u.get("email"), "error": str(e)[:220]})

        if sent % 100 == 0:
            await asyncio.sleep(0)

    if delivery_docs:
        await db[LEGAL_DELIVERY_COL].insert_many(delivery_docs)

    record = {
        "broadcast_id": broadcast_id,
        "kind": "legal_notice",
        "policy_type": body.policy_type,
        "effective_date": body.effective_date,
        "summary_of_changes": summary,
        "review_url": body.review_url or "",
        "audience": body.audience,
        "user_id_count": len(body.user_ids or []),
        "recipient_count": recipient_count,
        "sent_ok": sent,
        "sent_failed": failed,
        "tracked_message_count": len(delivery_docs),
        "broadcast_by": actor,
        "trigger": trigger,
        "schedule_id": schedule_id,
        "sent_at": sent_at,
        "dry_run": False,
        "errors": errors[:100],
    }
    await db[LEGAL_COL].insert_one(record)
    await _log_digest_entry_safe(
        kind="legal_notice_broadcast",
        subject=f"{body.policy_type} update — effective {body.effective_date}",
        summary=summary[:500],
        recipient_count=recipient_count,
        sent_ok=sent,
        sent_failed=failed,
        actor=actor,
    )

    return {
        "success": True,
        "broadcast_id": broadcast_id,
        "recipient_count": recipient_count,
        "sent_ok": sent,
        "sent_failed": failed,
        "tracked_message_count": len(delivery_docs),
        "errors": errors[:20],
        "preview": {
            "subject": f"Important: {body.policy_type} Updated — Effective {body.effective_date}",
            "policy_type": body.policy_type,
            "effective_date": body.effective_date,
            "summary": summary,
            "review_url": body.review_url,
            "audience": body.audience,
            "recipient_count": recipient_count,
        },
    }


@router.post("/admin/legal-notice/broadcast")
async def admin_legal_notice_broadcast(request: Request, body: LegalNoticeBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"

    if body.dry_run:
        users = await _target_users(body.audience, body.user_ids)
        return {
            "dry_run": True,
            "recipient_count": len(users),
            "audience": body.audience,
            "preview_subject": f"Important: {body.policy_type} Updated — Effective {body.effective_date}",
            "rate_limit_seconds": RATE_LIMIT_SECONDS,
        }

    _assert_confirm_phrase(body.confirm_phrase)
    return await _send_legal_notice_now(
        actor=actor,
        body=body,
        trigger="manual",
        schedule_id=None,
        enforce_rate_limit=True,
    )


@router.get("/admin/legal-notice/broadcasts")
async def admin_list_legal_broadcasts(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[LEGAL_COL].find({}, {"_id": 0}).sort("sent_at", -1).limit(limit):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.post("/admin/legal-notice/schedules")
async def create_legal_notice_schedule(request: Request, body: LegalScheduleCreateBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"

    scheduled_dt = _parse_iso_utc(body.scheduled_send_at)
    notification_dt = _parse_iso_utc(body.notification_send_at) if body.notification_send_at else None
    if body.audience == "affected_only" and not body.user_ids:
        raise HTTPException(status_code=400, detail="user_ids required when audience=affected_only")

    now_iso = _now_iso()
    schedule_id = f"ls_{uuid.uuid4().hex[:12]}"
    doc = {
        "schedule_id": schedule_id,
        "policy_type": body.policy_type,
        "effective_date": body.effective_date,
        "summary_of_changes": body.summary_of_changes.strip(),
        "review_url": body.review_url or "",
        "audience": body.audience,
        "user_ids": body.user_ids,
        "scheduled_send_at": scheduled_dt.isoformat(),
        "notification_send_at": notification_dt.isoformat() if notification_dt else None,
        "timezone": body.timezone or "UTC",
        "approval_required": bool(body.approval_required),
        "status": "draft",
        "created_by": actor,
        "created_at": now_iso,
        "updated_at": now_iso,
        "updated_by": actor,
    }
    await db[LEGAL_SCHEDULE_COL].insert_one(doc)
    await _append_legal_schedule_audit(schedule_id, "created", actor, {
        "policy_type": body.policy_type,
        "scheduled_send_at": doc["scheduled_send_at"],
        "approval_required": doc["approval_required"],
    })
    return {"success": True, "schedule": _serialize_schedule(doc)}


@router.get("/admin/legal-notice/schedules")
async def list_legal_notice_schedules(
    request: Request,
    status: Optional[str] = Query(default=None),
    policy_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    await require_admin(request)
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if policy_type:
        query["policy_type"] = policy_type
    rows = await db[LEGAL_SCHEDULE_COL].find(query, {"_id": 0}).sort("scheduled_send_at", -1).limit(limit).to_list(limit)
    return {"items": rows, "count": len(rows)}


@router.get("/admin/legal-notice/schedules/{schedule_id}")
async def get_legal_notice_schedule(request: Request, schedule_id: str):
    await require_admin(request)
    row = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": row}


@router.put("/admin/legal-notice/schedules/{schedule_id}")
async def update_legal_notice_schedule(request: Request, schedule_id: str, body: LegalScheduleUpdateBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    existing = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if existing.get("status") in {"executed", "cancelled", "failed", "processing"}:
        raise HTTPException(status_code=409, detail="Schedule cannot be modified in current state")

    updates: dict[str, Any] = {}
    if body.effective_date is not None:
        updates["effective_date"] = body.effective_date
    if body.summary_of_changes is not None:
        updates["summary_of_changes"] = body.summary_of_changes.strip()
    if body.review_url is not None:
        updates["review_url"] = body.review_url
    if body.audience is not None:
        updates["audience"] = body.audience
    if body.user_ids is not None:
        updates["user_ids"] = body.user_ids
    if body.scheduled_send_at is not None:
        updates["scheduled_send_at"] = _parse_iso_utc(body.scheduled_send_at).isoformat()
    if body.notification_send_at is not None:
        updates["notification_send_at"] = _parse_iso_utc(body.notification_send_at).isoformat()
    if body.timezone is not None:
        updates["timezone"] = body.timezone
    if body.approval_required is not None:
        updates["approval_required"] = body.approval_required

    if updates.get("audience") == "affected_only" and not (updates.get("user_ids") or existing.get("user_ids")):
        raise HTTPException(status_code=400, detail="user_ids required when audience=affected_only")

    updates["updated_at"] = _now_iso()
    updates["updated_by"] = actor
    await db[LEGAL_SCHEDULE_COL].update_one({"schedule_id": schedule_id}, {"$set": updates})
    await _append_legal_schedule_audit(schedule_id, "updated", actor, {"fields": sorted(updates.keys())})
    row = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    return {"success": True, "schedule": row}


@router.post("/admin/legal-notice/schedules/{schedule_id}/submit")
async def submit_legal_notice_schedule(request: Request, schedule_id: str):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    row = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if row.get("status") not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft/rejected schedules can be submitted")

    next_status = "pending_approval" if row.get("approval_required", True) else "approved"
    updates = {
        "status": next_status,
        "submitted_at": _now_iso(),
        "submitted_by": actor,
        "updated_at": _now_iso(),
        "updated_by": actor,
    }
    await db[LEGAL_SCHEDULE_COL].update_one({"schedule_id": schedule_id}, {"$set": updates})
    await _append_legal_schedule_audit(schedule_id, "submitted", actor, {"status": next_status})
    return {"success": True, "status": next_status}


@router.post("/admin/legal-notice/schedules/{schedule_id}/approve")
async def approve_legal_notice_schedule(request: Request, schedule_id: str, body: LegalScheduleDecisionBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    row = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if row.get("status") != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending_approval schedules can be approved")

    updates = {
        "status": "approved",
        "approved_at": _now_iso(),
        "approved_by": actor,
        "approval_note": body.note or "",
        "updated_at": _now_iso(),
        "updated_by": actor,
    }
    await db[LEGAL_SCHEDULE_COL].update_one({"schedule_id": schedule_id}, {"$set": updates})
    await _append_legal_schedule_audit(schedule_id, "approved", actor, {"note": body.note or ""})
    return {"success": True, "status": "approved"}


@router.post("/admin/legal-notice/schedules/{schedule_id}/reject")
async def reject_legal_notice_schedule(request: Request, schedule_id: str, body: LegalScheduleDecisionBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    row = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if row.get("status") != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending_approval schedules can be rejected")

    updates = {
        "status": "rejected",
        "rejected_at": _now_iso(),
        "rejected_by": actor,
        "rejection_note": body.note or "",
        "updated_at": _now_iso(),
        "updated_by": actor,
    }
    await db[LEGAL_SCHEDULE_COL].update_one({"schedule_id": schedule_id}, {"$set": updates})
    await _append_legal_schedule_audit(schedule_id, "rejected", actor, {"note": body.note or ""})
    return {"success": True, "status": "rejected"}


@router.post("/admin/legal-notice/schedules/{schedule_id}/cancel")
async def cancel_legal_notice_schedule(request: Request, schedule_id: str, body: LegalScheduleDecisionBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    row = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": schedule_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if row.get("status") in {"executed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Schedule cannot be cancelled in current state")

    updates = {
        "status": "cancelled",
        "cancelled_at": _now_iso(),
        "cancelled_by": actor,
        "cancel_note": body.note or "",
        "updated_at": _now_iso(),
        "updated_by": actor,
    }
    await db[LEGAL_SCHEDULE_COL].update_one({"schedule_id": schedule_id}, {"$set": updates})
    await _append_legal_schedule_audit(schedule_id, "cancelled", actor, {"note": body.note or ""})
    return {"success": True, "status": "cancelled"}


@router.get("/admin/legal-notice/schedules/{schedule_id}/audit")
async def get_legal_notice_schedule_audit(request: Request, schedule_id: str, limit: int = Query(default=100, ge=1, le=500)):
    await require_admin(request)
    rows = await db[LEGAL_SCHEDULE_AUDIT_COL].find({"schedule_id": schedule_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": rows, "count": len(rows)}


async def run_scheduled_legal_notice_broadcasts(batch_size: int = 25) -> dict:
    now_iso = _now_iso()
    due = await db[LEGAL_SCHEDULE_COL].find(
        {
            "status": "approved",
            "scheduled_send_at": {"$lte": now_iso},
        },
        {"_id": 0},
    ).sort("scheduled_send_at", 1).limit(batch_size).to_list(batch_size)

    processed = 0
    executed = 0
    failed = 0

    for row in due:
        schedule_id = row.get("schedule_id")
        if not schedule_id:
            continue

        lock = await db[LEGAL_SCHEDULE_COL].update_one(
            {"schedule_id": schedule_id, "status": "approved"},
            {"$set": {"status": "processing", "processing_at": now_iso}},
        )
        if lock.modified_count == 0:
            continue

        processed += 1
        actor = row.get("approved_by") or row.get("submitted_by") or "system:scheduler"
        try:
            body = LegalNoticeBody(
                policy_type=row.get("policy_type", "Terms of Service"),
                effective_date=row.get("effective_date", ""),
                summary_of_changes=row.get("summary_of_changes", ""),
                review_url=row.get("review_url") or "",
                audience=row.get("audience", "all_users"),
                user_ids=row.get("user_ids") or None,
                dry_run=False,
                confirm_phrase=CONFIRM_PHRASE,
            )
            result = await _send_legal_notice_now(
                actor=actor,
                body=body,
                trigger="scheduled",
                schedule_id=schedule_id,
                enforce_rate_limit=False,
            )
            await db[LEGAL_SCHEDULE_COL].update_one(
                {"schedule_id": schedule_id},
                {
                    "$set": {
                        "status": "executed",
                        "executed_at": _now_iso(),
                        "executed_broadcast_id": result.get("broadcast_id"),
                        "updated_at": _now_iso(),
                        "updated_by": "system:scheduler",
                    }
                },
            )
            await _append_legal_schedule_audit(schedule_id, "executed", "system:scheduler", {
                "broadcast_id": result.get("broadcast_id"),
                "sent_ok": result.get("sent_ok", 0),
                "sent_failed": result.get("sent_failed", 0),
            })
            executed += 1
        except Exception as e:
            await db[LEGAL_SCHEDULE_COL].update_one(
                {"schedule_id": schedule_id},
                {
                    "$set": {
                        "status": "failed",
                        "failed_at": _now_iso(),
                        "last_error": str(e)[:500],
                        "updated_at": _now_iso(),
                        "updated_by": "system:scheduler",
                    }
                },
            )
            await _append_legal_schedule_audit(schedule_id, "failed", "system:scheduler", {"error": str(e)[:300]})
            failed += 1

    return {
        "processed": processed,
        "executed": executed,
        "failed": failed,
        "checked_at": now_iso,
    }


@router.get("/admin/legal-notice/engagement")
async def get_legal_notice_engagement(
    request: Request,
    days: int = Query(default=30, ge=1, le=180),
    policy_type: Optional[str] = Query(default=None),
):
    await require_admin(request)
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    broadcast_query: dict[str, Any] = {
        "dry_run": {"$ne": True},
        "sent_at": {"$gte": cutoff_iso},
    }
    if policy_type:
        broadcast_query["policy_type"] = policy_type

    broadcasts = await db[LEGAL_COL].find(broadcast_query, {"_id": 0}).sort("sent_at", -1).to_list(1000)
    if not broadcasts:
        return {
            "window_days": days,
            "totals": {
                "campaigns": 0,
                "sent": 0,
                "failed": 0,
                "delivered": 0,
                "opened": 0,
                "clicked": 0,
                "open_rate": 0,
                "click_rate": 0,
            },
            "by_policy": [],
            "recent_campaigns": [],
            "notes": "No legal notice broadcasts in requested window.",
        }

    broadcast_ids = [b.get("broadcast_id") for b in broadcasts if b.get("broadcast_id")]
    deliveries = await db[LEGAL_DELIVERY_COL].find(
        {"broadcast_id": {"$in": broadcast_ids}},
        {"_id": 0, "broadcast_id": 1, "policy_type": 1, "email_id": 1},
    ).to_list(150000)

    delivery_by_policy: dict[str, set[str]] = defaultdict(set)
    delivery_by_campaign: dict[str, set[str]] = defaultdict(set)
    all_email_ids: set[str] = set()
    for d in deliveries:
        email_id = str(d.get("email_id") or "").strip()
        if not email_id:
            continue
        policy = str(d.get("policy_type") or "Unknown")
        campaign = str(d.get("broadcast_id") or "")
        all_email_ids.add(email_id)
        delivery_by_policy[policy].add(email_id)
        if campaign:
            delivery_by_campaign[campaign].add(email_id)

    event_rows = []
    if all_email_ids:
        event_rows = await db.email_delivery_events.find(
            {
                "email_id": {"$in": list(all_email_ids)},
                "internal_status": {"$in": ["delivered", "opened", "clicked", "bounced", "complained"]},
            },
            {"_id": 0, "email_id": 1, "internal_status": 1},
        ).to_list(300000)

    status_sets: dict[str, set[str]] = defaultdict(set)
    for e in event_rows:
        eid = str(e.get("email_id") or "").strip()
        st = str(e.get("internal_status") or "").strip().lower()
        if eid and st:
            status_sets[st].add(eid)

    def _rate(n: int, d: int) -> float:
        return round((n / d) * 100, 2) if d else 0.0

    totals_sent = sum(int(b.get("sent_ok") or 0) for b in broadcasts)
    totals_failed = sum(int(b.get("sent_failed") or 0) for b in broadcasts)
    delivered_count = len(status_sets.get("delivered", set()) & all_email_ids)
    opened_count = len(status_sets.get("opened", set()) & all_email_ids)
    clicked_count = len(status_sets.get("clicked", set()) & all_email_ids)

    policy_aggregate: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "campaigns": 0,
        "sent": 0,
        "failed": 0,
        "tracked": 0,
        "delivered": 0,
        "opened": 0,
        "clicked": 0,
    })
    for b in broadcasts:
        policy = str(b.get("policy_type") or "Unknown")
        agg = policy_aggregate[policy]
        agg["campaigns"] += 1
        agg["sent"] += int(b.get("sent_ok") or 0)
        agg["failed"] += int(b.get("sent_failed") or 0)

    for policy, ids in delivery_by_policy.items():
        agg = policy_aggregate[policy]
        agg["tracked"] = len(ids)
        agg["delivered"] = len(status_sets.get("delivered", set()) & ids)
        agg["opened"] = len(status_sets.get("opened", set()) & ids)
        agg["clicked"] = len(status_sets.get("clicked", set()) & ids)

    by_policy = []
    for policy, agg in sorted(policy_aggregate.items(), key=lambda kv: kv[0]):
        sent_base = agg["tracked"] or agg["sent"]
        by_policy.append({
            "policy_type": policy,
            "campaigns": agg["campaigns"],
            "sent": agg["sent"],
            "failed": agg["failed"],
            "tracked_messages": agg["tracked"],
            "delivered": agg["delivered"],
            "opened": agg["opened"],
            "clicked": agg["clicked"],
            "open_rate": _rate(agg["opened"], sent_base),
            "click_rate": _rate(agg["clicked"], sent_base),
            "click_to_open_rate": _rate(agg["clicked"], agg["opened"]),
        })

    recent_campaigns = []
    for b in broadcasts[:25]:
        bid = b.get("broadcast_id")
        tracked_ids = delivery_by_campaign.get(bid, set())
        opened = len(status_sets.get("opened", set()) & tracked_ids)
        clicked = len(status_sets.get("clicked", set()) & tracked_ids)
        base = len(tracked_ids) or int(b.get("sent_ok") or 0)
        recent_campaigns.append({
            "broadcast_id": bid,
            "policy_type": b.get("policy_type"),
            "trigger": b.get("trigger", "manual"),
            "schedule_id": b.get("schedule_id"),
            "sent_at": b.get("sent_at"),
            "sent_ok": int(b.get("sent_ok") or 0),
            "sent_failed": int(b.get("sent_failed") or 0),
            "tracked_messages": len(tracked_ids),
            "opened": opened,
            "clicked": clicked,
            "open_rate": _rate(opened, base),
            "click_rate": _rate(clicked, base),
        })

    return {
        "window_days": days,
        "totals": {
            "campaigns": len(broadcasts),
            "sent": totals_sent,
            "failed": totals_failed,
            "tracked_messages": len(all_email_ids),
            "delivered": delivered_count,
            "opened": opened_count,
            "clicked": clicked_count,
            "open_rate": _rate(opened_count, len(all_email_ids) or totals_sent),
            "click_rate": _rate(clicked_count, len(all_email_ids) or totals_sent),
            "click_to_open_rate": _rate(clicked_count, opened_count),
        },
        "by_policy": by_policy,
        "recent_campaigns": recent_campaigns,
        "notes": "Open/click metrics are computed from webhook delivery events for tracked legal send message_ids.",
    }


@router.post("/admin/legal-notice/suggestion-feedback")
async def log_legal_suggestion_feedback(request: Request, body: LegalSuggestionFeedbackBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"

    if body.schedule_id:
        schedule_exists = await db[LEGAL_SCHEDULE_COL].find_one({"schedule_id": body.schedule_id}, {"_id": 0})
        if not schedule_exists:
            raise HTTPException(status_code=404, detail="Schedule not found")

    audit_scope = body.schedule_id or "global-ai-suggestions"
    action = "ai_suggestion_accepted" if body.decision == "accepted" else "ai_suggestion_rejected"
    event = await _append_legal_schedule_audit(
        audit_scope,
        action,
        actor,
        {
            "policy_type": body.policy_type,
            "intent": body.intent,
            "style_preset": body.style_preset,
            "decision": body.decision,
            "source": body.source,
            "confidence": body.confidence,
            "summary_length": body.summary_length,
            "note": body.note or "",
        },
    )
    return {
        "success": True,
        "event_id": event.get("event_id"),
        "schedule_scope": audit_scope,
    }


@router.get("/admin/legal-notice/suggestion-analytics")
async def get_legal_suggestion_analytics(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    schedule_id: Optional[str] = Query(default=None),
):
    await require_admin(request)
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query: dict[str, Any] = {
        "action": {"$in": ["ai_suggestion_accepted", "ai_suggestion_rejected"]},
        "created_at": {"$gte": cutoff_iso},
    }
    if schedule_id:
        query["schedule_id"] = schedule_id

    rows = await db[LEGAL_SCHEDULE_AUDIT_COL].find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)

    by_intent: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "used": 0,
        "accepted": 0,
        "rejected": 0,
        "accept_rate": 0.0,
    })
    by_style: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "used": 0,
        "accepted": 0,
        "rejected": 0,
        "accept_rate": 0.0,
    })

    for row in rows:
        details = row.get("details") or {}
        intent = str(details.get("intent") or "unknown")
        style = str(details.get("style_preset") or "unspecified")
        decision = str(details.get("decision") or "").lower()

        by_intent[intent]["used"] += 1
        by_style[style]["used"] += 1
        if decision == "accepted":
            by_intent[intent]["accepted"] += 1
            by_style[style]["accepted"] += 1
        elif decision == "rejected":
            by_intent[intent]["rejected"] += 1
            by_style[style]["rejected"] += 1

    for bucket in (by_intent, by_style):
        for key, metric in bucket.items():
            metric["accept_rate"] = round((metric["accepted"] / metric["used"]) * 100, 2) if metric["used"] else 0.0

    recent = []
    for row in rows[:25]:
        details = row.get("details") or {}
        recent.append({
            "event_id": row.get("event_id"),
            "created_at": row.get("created_at"),
            "actor": row.get("actor"),
            "schedule_id": row.get("schedule_id"),
            "decision": details.get("decision"),
            "intent": details.get("intent"),
            "style_preset": details.get("style_preset"),
            "policy_type": details.get("policy_type"),
            "confidence": details.get("confidence"),
        })

    return {
        "window_days": days,
        "scope": schedule_id or "all",
        "total_events": len(rows),
        "by_intent": dict(by_intent),
        "by_style": dict(by_style),
        "recent_events": recent,
    }


# ─────────────────────────────────────────────────────────────────────────
# 2) Security Incident Broadcast (breach / cyberattack)
# ─────────────────────────────────────────────────────────────────────────


INCIDENT_TYPES = {
    "data_breach",
    "unauthorized_access",
    "cyberattack",
    "credential_leak",
    "third_party_vendor_incident",
    "phishing_campaign",
    "other",
}
SEVERITIES = {"critical", "high", "medium", "informational"}
PUSH_SEVERITY_DEFAULT = {"critical", "high"}  # push ON by default for these

# Security Incident broadcasts MUST be signed with one of the canonical
# incident-response contact addresses. A prior incident showed that
# leaving `contact_email` as a free-text EmailStr lets a well-meaning
# operator (or a buggy automation) sign a security broadcast with an
# unrelated address like `hiring@realaicoach.app` — which erodes trust,
# routes user replies to the wrong inbox, and leaks role info to
# recipients. This allowlist is the second line of defence after the
# pre-filled value in SecurityIncidentBroadcastPanel.tsx.
#
# If you need to add a new allowed local-part, coordinate with the
# security team AND update the default in
# `utils/email_templates.py::build_security_incident_email` to match.
_SECURITY_INCIDENT_ALLOWED_LOCAL_PARTS = frozenset({
    "security",
    "privacy",
    "support",
    "trust",
    "abuse",
    "incident",
    "incident-response",
})


class SecurityIncidentBody(BaseModel):
    incident_type: str = Field(..., max_length=64)
    severity: str = Field(..., max_length=32)
    incident_date: str = Field(..., max_length=80)
    discovered_date: str = Field(..., max_length=80)
    what_happened: str = Field(..., min_length=10, max_length=2000)
    data_affected: str = Field(..., min_length=2, max_length=500)
    user_action_required: str = Field(..., min_length=2, max_length=500)
    remediation_steps: str = Field(..., min_length=2, max_length=1000)
    contact_email: EmailStr
    action_url: Optional[str] = Field(None, max_length=500)
    audience: Literal["all_users", "affected_only"] = "affected_only"
    user_ids: Optional[list[str]] = None
    # Push channel options
    push_enabled: Optional[bool] = None  # default: True for critical/high
    push_mode: Literal["full_detail", "minimal_deeplink"] = "minimal_deeplink"
    dry_run: bool = True
    confirm_phrase: Optional[str] = None

    @field_validator("contact_email")
    @classmethod
    def _contact_email_must_be_role_based(cls, value: str) -> str:
        """Reject contact emails whose local-part isn't in the
        incident-response allowlist. Prevents signing a security
        broadcast with an unrelated inbox like `hiring@`, `ceo@`, or a
        personal address."""
        local_part = (value or "").strip().lower().split("@", 1)[0]
        if local_part not in _SECURITY_INCIDENT_ALLOWED_LOCAL_PARTS:
            allowed = ", ".join(sorted(_SECURITY_INCIDENT_ALLOWED_LOCAL_PARTS))
            raise ValueError(
                f"contact_email local-part '{local_part}' is not a recognised "
                f"incident-response address. Allowed local-parts: {allowed}. "
                f"Use security@<domain> as the default — see "
                f"SecurityIncidentBroadcastPanel.tsx which pre-fills it."
            )
        return value


def _pretty_incident_type(raw: str) -> str:
    return raw.replace("_", " ").title() if raw else "Security Incident"


def _resolve_push_enabled(severity: str, explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return bool(explicit)
    return severity in PUSH_SEVERITY_DEFAULT


def _push_copy(mode: str, incident_label: str, user_action_required: str) -> tuple[str, str]:
    """Return (title, body) for the push notification. Two modes:
      - full_detail: direct instruction, max protective
      - minimal_deeplink: calmer tone, nudges user to open app for detail
    """
    if mode == "full_detail":
        return (
            f"{incident_label} — action required",
            user_action_required[:140],
        )
    return (
        "Important security notice",
        "Tap to read an urgent security notice from us.",
    )


@router.post("/admin/security-incident/broadcast")
async def admin_security_incident_broadcast(request: Request, body: SecurityIncidentBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"

    # Validate enums in-route so the error message is actionable rather
    # than a generic pydantic Literal noise.
    if body.incident_type not in INCIDENT_TYPES:
        raise HTTPException(status_code=400, detail=f"incident_type must be one of {sorted(INCIDENT_TYPES)}")
    sev = body.severity.lower()
    if sev not in SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {sorted(SEVERITIES)}")

    users = await _target_users(body.audience, body.user_ids)
    recipient_count = len(users)
    push_enabled = _resolve_push_enabled(sev, body.push_enabled)
    incident_label = _pretty_incident_type(body.incident_type)

    if body.dry_run:
        return {
            "dry_run": True,
            "recipient_count": recipient_count,
            "audience": body.audience,
            "severity": sev,
            "incident_type": body.incident_type,
            "push_enabled": push_enabled,
            "push_mode": body.push_mode,
            "preview_subject": f"Important Security Notice — {incident_label} ({sev.title()})",
            "rate_limit_seconds": RATE_LIMIT_SECONDS,
        }

    _assert_confirm_phrase(body.confirm_phrase)
    await _rate_limit_or_raise(actor, SEC_COL)

    from utils.email_service import send_catalog_template, is_email_configured
    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service is not configured.")

    # Push helper imported lazily — notifications module is heavy and
    # this endpoint is only hit during an active incident.
    push_sender = None
    if push_enabled:
        try:
            from routes.notifications import send_push_notification  # type: ignore
            push_sender = send_push_notification
        except Exception as e:
            logger.warning(f"[security-incident] push unavailable: {e}")
            push_sender = None

    push_title, push_body = _push_copy(body.push_mode, incident_label, body.user_action_required)
    push_data = {
        "kind": "security_incident",
        "severity": sev,
        "incident_type": body.incident_type,
        "action_url": body.action_url or "/account/security",
    }

    sent_email, failed_email = 0, 0
    sent_push, failed_push = 0, 0

    async def _fanout_one(u: dict[str, Any]) -> None:
        nonlocal sent_email, failed_email, sent_push, failed_push
        try:
            await send_catalog_template(
                recipient_email=u["email"],
                template_key="security_incident_notice",
                recipient_name=u.get("name", ""),
                user_name=u.get("name") or "there",
                incident_type=incident_label,
                severity=sev,
                incident_date=body.incident_date,
                discovered_date=body.discovered_date,
                what_happened=body.what_happened,
                data_affected=body.data_affected,
                user_action_required=body.user_action_required,
                remediation_steps=body.remediation_steps,
                contact_email=str(body.contact_email),
                action_url=body.action_url or "",
            )
            sent_email += 1
        except Exception as e:
            logger.warning(f"[security-incident] email failed for {u.get('email')}: {e}")
            failed_email += 1
        if push_sender is not None:
            try:
                ok = await push_sender(u["user_id"], push_title, push_body, push_data)
                if ok:
                    sent_push += 1
            except Exception as e:
                logger.warning(f"[security-incident] push failed for {u.get('user_id')}: {e}")
                failed_push += 1

    # Fan out with modest concurrency — too parallel burns downstream
    # rate limits (Resend, Expo) in a breach scenario.
    sem = asyncio.Semaphore(10)

    async def _bounded(u: dict[str, Any]) -> None:
        async with sem:
            await _fanout_one(u)

    await asyncio.gather(*(_bounded(u) for u in users), return_exceptions=True)

    record = {
        "broadcast_id": f"sec_{uuid.uuid4().hex[:12]}",
        "kind": "security_incident",
        "incident_type": body.incident_type,
        "severity": sev,
        "incident_date": body.incident_date,
        "discovered_date": body.discovered_date,
        "what_happened": body.what_happened,
        "data_affected": body.data_affected,
        "user_action_required": body.user_action_required,
        "remediation_steps": body.remediation_steps,
        "contact_email": str(body.contact_email),
        "action_url": body.action_url or "",
        "audience": body.audience,
        "user_id_count": len(body.user_ids or []),
        "recipient_count": recipient_count,
        "sent_email": sent_email,
        "failed_email": failed_email,
        "push_enabled": push_enabled,
        "push_mode": body.push_mode,
        "sent_push": sent_push,
        "failed_push": failed_push,
        "broadcast_by": actor,
        "sent_at": _now_iso(),
        "dry_run": False,
    }
    await db[SEC_COL].insert_one(record)
    record.pop("_id", None)

    await _log_digest_entry_safe(
        kind="security_incident_broadcast",
        subject=f"Security notice: {incident_label} ({sev}) — {recipient_count} users",
        summary=body.what_happened[:500],
        recipient_count=recipient_count,
        sent_ok=sent_email,
        sent_failed=failed_email,
        actor=actor,
    )

    # Also ping admin bus so on-call admins see this in their live alert
    # stream — important because starting a breach broadcast is itself a
    # change-management event other admins should know about.
    try:
        from routes.admin_push_notifications import emit_realtime_alert
        await emit_realtime_alert(
            "security_incident_broadcast_sent",
            "critical" if sev in ("critical", "high") else "warning",
            f"Security notice sent — {incident_label}",
            f"{sent_email}/{recipient_count} emails delivered by {actor}. "
            + (f"{sent_push} pushes sent." if push_enabled else "No push channel."),
        )
    except Exception as e:
        logger.debug(f"[security-incident] admin bus ping skipped: {e}")

    return record


@router.get("/admin/security-incident/broadcasts")
async def admin_list_security_broadcasts(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[SEC_COL].find({}, {"_id": 0}).sort("sent_at", -1).limit(limit):
        items.append(d)
    return {"items": items, "count": len(items)}


__all__ = [
    "router",
    "LEGAL_COL",
    "LEGAL_SCHEDULE_COL",
    "LEGAL_SCHEDULE_AUDIT_COL",
    "LEGAL_DELIVERY_COL",
    "SEC_COL",
    "RATE_LIMIT_SECONDS",
    "CONFIRM_PHRASE",
    "INCIDENT_TYPES",
    "SEVERITIES",
    "run_scheduled_legal_notice_broadcasts",
]
