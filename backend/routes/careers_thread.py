"""Careers Applicant Thread — auto-thread inbound applicant replies.

Endpoints
---------
POST /api/webhooks/inbound-email
    Provider-agnostic ingress for inbound email. When the sender replies
    to a `career_confirmation` email (to ``hiring+APP-XXX@...`` or
    keeping ``[APP-XXX]`` in the subject), this handler correlates the
    message to the application and appends it to the thread.

    HMAC-verified via the ``X-Webhook-Secret`` header against the
    ``INBOUND_EMAIL_WEBHOOK_SECRET`` env var. If the secret is not
    configured, verification is skipped (dev / bootstrap mode) — the
    response still confirms whether correlation happened.

GET /api/careers/applications/{application_id}/thread
    Admin-only listing of all messages (inbound + outbound) correlated
    to a single application, chronologically ascending.

Collection
----------
``careers_application_threads`` — one document per message:
    thread_id, application_id, direction (outbound|inbound),
    from_email, to_email, subject, body_text, body_html,
    message_id, in_reply_to, correlation_signal,
    received_at, created_at.
"""
from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import require_admin
import routes.db as _db_mod
from utils.careers_thread_correlator import correlate_inbound

# Canonical admin dependency alias for backward compatibility
_require_admin = require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

THREAD_COL = "careers_application_threads"
APPS_COL = "careers_applications"


def _verify_inbound_secret(request: Request) -> bool:
    """Compare ``X-Webhook-Secret`` against env ``INBOUND_EMAIL_WEBHOOK_SECRET``.

    Constant-time compare. When the env var is unset, verification is
    skipped (first-run / dev). Ops must set the secret before flipping
    DNS/MX to this endpoint.
    """
    expected = os.environ.get("INBOUND_EMAIL_WEBHOOK_SECRET", "").strip()
    if not expected:
        return True
    supplied = (request.headers.get("x-webhook-secret") or "").strip()
    if not supplied:
        return False
    return hmac.compare_digest(expected, supplied)


async def _resolve_app_from_message_refs(refs: list[str]) -> Optional[str]:
    """Look up an application_id by outbound Message-IDs stored in threads."""
    if not refs:
        return None
    doc = await _db_mod.db[THREAD_COL].find_one(
        {"message_id": {"$in": refs}, "direction": "outbound"},
        {"_id": 0, "application_id": 1},
    )
    return doc.get("application_id") if doc else None


async def append_thread_message(
    application_id: str,
    direction: str,
    from_email: str,
    to_email: str,
    subject: str,
    body_text: str = "",
    body_html: str = "",
    message_id: str = "",
    in_reply_to: str = "",
    correlation_signal: str = "",
    attachments: Optional[list] = None,
) -> dict[str, Any]:
    """Insert a thread entry. Also pokes the application's unread counter."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "thread_id": f"thr_{uuid.uuid4().hex[:16]}",
        "application_id": application_id,
        "direction": direction,
        "from_email": (from_email or "").strip().lower(),
        "to_email": (to_email or "").strip().lower(),
        "subject": subject or "",
        "body_text": (body_text or "")[:20000],
        "body_html": (body_html or "")[:100000],
        "message_id": (message_id or "").strip(),
        "in_reply_to": (in_reply_to or "").strip(),
        "correlation_signal": correlation_signal or "",
        "attachments": attachments or [],
        "received_at": now,
        "created_at": now,
    }
    await _db_mod.db[THREAD_COL].insert_one(doc)
    # Bump applicant record so recruiter sees the unread badge.
    if direction == "inbound":
        try:
            await _db_mod.db[APPS_COL].update_one(
                {"application_id": application_id},
                {
                    "$set": {
                        "last_applicant_reply_at": now,
                        "last_applicant_reply_from": doc["from_email"],
                    },
                    "$inc": {"unread_applicant_replies": 1},
                },
            )
        except Exception as e:  # pragma: no cover
            logger.warning(f"[careers-thread] unread bump failed: {e}")
    return {k: v for k, v in doc.items() if k != "_id"}


# ── Inbound webhook ──────────────────────────────────────────────────────
@router.post("/webhooks/inbound-email")
async def inbound_email_webhook(request: Request) -> dict[str, Any]:
    """Receive an inbound email and append it to the applicant thread if we
    can correlate it to an application. Returns a structured status so the
    provider dashboard can show whether correlation happened.

    Accepted payload shape (provider-agnostic JSON):
        {
          "from": "applicant@example.com",
          "to": ["hiring+APP-XXXX@realaicoach.app"],
          "subject": "Re: Application Received ... [APP-XXXX]",
          "text": "plain body",
          "html": "<p>html body</p>",
          "message_id": "<abc@mail.example.com>",
          "in_reply_to": "<outbound-id@resend...>",
          "references": "<r1@...> <r2@...>",
          "attachments": [{"filename": "...", "url": "..."}]
        }
    """
    if not _verify_inbound_secret(request):
        raise HTTPException(status_code=401, detail="Invalid inbound webhook secret")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    from_email = str(payload.get("from") or "").strip()
    raw_to = payload.get("to") or []
    if isinstance(raw_to, str):
        to_list = [raw_to]
    else:
        to_list = [str(x) for x in raw_to]
    subject = str(payload.get("subject") or "")
    in_reply_to = str(payload.get("in_reply_to") or "")
    references = str(payload.get("references") or "")
    message_id = str(payload.get("message_id") or "")
    text = str(payload.get("text") or "")
    html = str(payload.get("html") or "")
    attachments = payload.get("attachments") or []

    app_id, signal = correlate_inbound(to_list, subject, in_reply_to, references)

    # Fallback: if correlator returned refs for DB lookup, resolve now.
    if not app_id and signal.startswith("message_id_refs:"):
        refs = signal.split(":", 1)[1].split(",") if ":" in signal else []
        resolved = await _resolve_app_from_message_refs(refs)
        if resolved:
            app_id = resolved
            signal = "message_id_refs"

    if not app_id:
        logger.info(
            f"[careers-thread] inbound reply uncorrelated — from={from_email[:120]} "
            f"to={to_list} subject={subject[:120]!r}"
        )
        # Store into a dead-letter collection so ops can triage orphans.
        try:
            await _db_mod.db["careers_thread_orphans"].insert_one(
                {
                    "orphan_id": f"orph_{uuid.uuid4().hex[:16]}",
                    "from_email": from_email.lower(),
                    "to_list": to_list,
                    "subject": subject,
                    "message_id": message_id,
                    "in_reply_to": in_reply_to,
                    "references": references,
                    "text": text[:10000],
                    "html": html[:50000],
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as e:  # pragma: no cover
            logger.warning(f"[careers-thread] orphan insert failed: {e}")
        return {"correlated": False, "reason": "no_correlation", "signal": signal}

    # Confirm the application exists (defensive — protects against malicious
    # callers inventing APP-IDs).
    app_doc = await _db_mod.db[APPS_COL].find_one(
        {"application_id": app_id}, {"_id": 0, "application_id": 1, "email": 1}
    )
    if not app_doc:
        logger.warning(
            f"[careers-thread] correlated app_id={app_id} does not exist — dropping"
        )
        return {"correlated": False, "reason": "unknown_application", "app_id": app_id}

    primary_to = to_list[0] if to_list else ""
    inserted = await append_thread_message(
        application_id=app_id,
        direction="inbound",
        from_email=from_email,
        to_email=primary_to,
        subject=subject,
        body_text=text,
        body_html=html,
        message_id=message_id,
        in_reply_to=in_reply_to,
        correlation_signal=signal,
        attachments=attachments,
    )
    logger.info(
        f"[careers-thread] inbound reply threaded — app_id={app_id} signal={signal} "
        f"thread_id={inserted['thread_id']}"
    )
    return {
        "correlated": True,
        "application_id": app_id,
        "thread_id": inserted["thread_id"],
        "signal": signal,
    }


# ── Admin thread listing ─────────────────────────────────────────────────
class ThreadMessage(BaseModel):
    thread_id: str
    application_id: str
    direction: str
    from_email: str
    to_email: str
    subject: str
    body_text: str = ""
    body_html: str = ""
    message_id: str = ""
    in_reply_to: str = ""
    correlation_signal: str = ""
    attachments: list = Field(default_factory=list)
    received_at: str
    created_at: str


class ThreadResponse(BaseModel):
    application_id: str
    messages: list[ThreadMessage]
    total: int
    unread_inbound: int


@router.get("/careers/applications/{application_id}/thread", response_model=ThreadResponse)
async def get_application_thread(application_id: str, request: Request) -> ThreadResponse:
    await _require_admin(request)

    app_doc = await _db_mod.db[APPS_COL].find_one(
        {"application_id": application_id},
        {"_id": 0, "application_id": 1, "unread_applicant_replies": 1},
    )
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    messages: list[ThreadMessage] = []
    cursor = (
        _db_mod.db[THREAD_COL]
        .find({"application_id": application_id}, {"_id": 0})
        .sort("received_at", 1)
    )
    async for doc in cursor:
        messages.append(ThreadMessage(**doc))

    return ThreadResponse(
        application_id=application_id,
        messages=messages,
        total=len(messages),
        unread_inbound=int(app_doc.get("unread_applicant_replies") or 0),
    )


@router.post("/careers/applications/{application_id}/thread/mark-read")
async def mark_thread_read(application_id: str, request: Request) -> dict[str, Any]:
    await _require_admin(request)
    result = await _db_mod.db[APPS_COL].update_one(
        {"application_id": application_id},
        {"$set": {"unread_applicant_replies": 0}},
    )
    return {"ok": True, "matched": result.matched_count}


# ── Recruiter outbound reply ────────────────────────────────────────────
class ReplyPayload(BaseModel):
    subject: str = Field("", max_length=400)
    body: str = Field(..., min_length=1, max_length=20000)


@router.post("/careers/applications/{application_id}/thread/reply")
async def reply_to_applicant(
    application_id: str, payload: ReplyPayload, request: Request
) -> dict[str, Any]:
    """Recruiter-side outbound reply to an applicant, threaded back onto
    the applicant record. Uses the same plus-address Reply-To + subject
    token so the applicant's reply will auto-correlate on the next round.
    """
    user = await _require_admin(request)

    app_doc = await _db_mod.db[APPS_COL].find_one(
        {"application_id": application_id},
        {"_id": 0, "application_id": 1, "email": 1, "name": 1, "role_title": 1},
    )
    if not app_doc or not app_doc.get("email"):
        raise HTTPException(status_code=404, detail="Application not found")

    recipient = app_doc["email"]
    recipient_name = app_doc.get("name") or ""
    role_title = app_doc.get("role_title") or "Open Application"

    hiring_inbox = (
        os.environ.get("CAREERS_HIRING_INBOX", "hiring@realaicoach.app") or ""
    ).strip()
    reply_to_addr = ""
    if "@" in hiring_inbox:
        _local, _domain = hiring_inbox.split("@", 1)
        reply_to_addr = f"{_local}+{application_id}@{_domain}"

    body_text = payload.body.strip()

    # Ensure subject carries [APP-XXX] so future replies correlate.
    subject = (payload.subject or "").strip() or f"Re: Your application for {role_title}"
    if f"[{application_id}]" not in subject:
        subject = f"{subject} [{application_id}]"

    # Send via the registered V7 template builder — this guarantees the
    # em-outer fingerprint the v7 HTML guardrail requires. The template
    # returns the full HTML; `send_catalog_template` forwards reply_to +
    # headers through to Resend for thread correlation.
    from utils.email_service import is_email_configured, send_catalog_template

    sent_message_id = ""
    body_html = ""
    if is_email_configured():
        result = await send_catalog_template(
            recipient_email=recipient,
            template_key="career_recruiter_reply",
            recipient_name=recipient_name,
            applicant_name=recipient_name,
            position=role_title,
            application_id=application_id,
            body_text=body_text,
            subject=subject,
            hiring_contact_email=hiring_inbox,
            reply_to=[reply_to_addr] if reply_to_addr else None,
            headers={
                "X-Application-ID": application_id,
                "X-RAC-Thread": "careers",
            },
        )
        if not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=f"Email dispatch failed: {result.get('error') or 'unknown'}",
            )
        sent_message_id = result.get("message_id") or ""
    else:
        logger.warning(
            "[careers-thread] reply sent via dry-run — email provider not configured"
        )

    # Persist outbound thread entry.
    inserted = await append_thread_message(
        application_id=application_id,
        direction="outbound",
        from_email=hiring_inbox,
        to_email=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        message_id=sent_message_id,
        correlation_signal="recruiter_reply",
    )

    # Clearing unread — recruiter acknowledged the thread by replying.
    await _db_mod.db[APPS_COL].update_one(
        {"application_id": application_id},
        {"$set": {"unread_applicant_replies": 0, "last_recruiter_reply_at": inserted["created_at"]}},
    )

    logger.info(
        f"[careers-thread] outbound recruiter reply sent — app_id={application_id} "
        f"thread_id={inserted['thread_id']} user={getattr(user, 'email', '?')}"
    )
    return {
        "ok": True,
        "thread_id": inserted["thread_id"],
        "message_id": sent_message_id,
        "subject": subject,
    }


# ── Dashboard summary (unread across all applications) ────────────────
@router.get("/careers/dashboard/unread-summary")
async def unread_summary(request: Request) -> dict[str, Any]:
    await _require_admin(request)
    total_apps_needing_response = await _db_mod.db[APPS_COL].count_documents(
        {"unread_applicant_replies": {"$gt": 0}}
    )
    # Sum of unread across all apps (for total messages badge).
    pipeline = [
        {"$match": {"unread_applicant_replies": {"$gt": 0}}},
        {
            "$group": {
                "_id": None,
                "total_unread": {"$sum": "$unread_applicant_replies"},
            }
        },
    ]
    total_unread = 0
    async for doc in _db_mod.db[APPS_COL].aggregate(pipeline):
        total_unread = int(doc.get("total_unread") or 0)
        break
    return {
        "applications_needing_response": int(total_apps_needing_response),
        "total_unread_messages": total_unread,
    }
