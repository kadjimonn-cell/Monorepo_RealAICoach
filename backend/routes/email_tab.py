"""Admin Email Tab — view user inquiries and reply via Resend email service."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from .db import db, require_admin
from utils.email_service import send_email, is_email_configured
from utils.field_encryption import decrypt_doc

logger = logging.getLogger(__name__)
router = APIRouter()

_CONTACT_ENC_FIELDS = ("name", "email", "message", "ip")


class ReplyRequest(BaseModel):
    message_id: str
    subject: Optional[str] = None
    body: str


class ComposeRequest(BaseModel):
    recipient_email: str
    subject: str
    body: str


def _build_reply_html(body: str, original_subject: str = "") -> str:
    """Build the admin reply body through the V7 `_wrap()` shell so the
    rendered email carries the `em-outer` fingerprint and survives the
    hard-block guardrail at utils/email_service.py (no more raw-HTML auto-wrap)."""
    # Lazy import avoids a circular dep with utils.email_service via utils.email_templates
    from utils.email_templates import _wrap, _lead, DASH_URL
    safe_body = body.replace("\r\n", "\n").replace("\n", "<br/>")
    inner = (
        _lead(
            "RealAICoach Support",
            f"This is a reply to your inquiry{f': <em>{original_subject}</em>' if original_subject else ''}.",
        )
        + f'<p class="em-text" style="color:#374151;font-size:14px;line-height:1.7;white-space:pre-wrap;margin:12px 0 0;">{safe_body}</p>'
    )
    return _wrap(
        "Support Reply",
        "A support agent responded to your message",
        inner,
        "Open Support",
        f"{DASH_URL}/support",
        category="support",
    )


@router.get("/admin/emails")
async def get_emails(req: Request, status: Optional[str] = None):
    await require_admin(req)
    query: dict = {}
    if status and status != "all":
        query["status"] = status
    emails = await db.contact_submissions.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    for e in emails:
        decrypt_doc(e, _CONTACT_ENC_FIELDS)
    # Count by status
    total = await db.contact_submissions.count_documents({})
    unread = await db.contact_submissions.count_documents({"status": {"$in": ["new", "pending", None]}})
    replied = await db.contact_submissions.count_documents({"status": "replied"})
    return {"emails": emails, "total": total, "unread": unread, "replied": replied}


@router.post("/admin/emails/read/{message_id}")
async def mark_email_read(message_id: str, req: Request):
    await require_admin(req)
    await db.contact_submissions.update_one(
        {"submission_id": message_id},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True}


@router.post("/admin/emails/reply")
async def reply_email(payload: ReplyRequest, req: Request):
    admin = await require_admin(req)

    # Find the original submission
    submission = await db.contact_submissions.find_one({"submission_id": payload.message_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Message not found")
    decrypt_doc(submission, _CONTACT_ENC_FIELDS)

    recipient_email = submission.get("email") or submission.get("user_email")
    if not recipient_email:
        raise HTTPException(status_code=400, detail="No recipient email found for this message")

    original_subject = submission.get("subject", submission.get("category", "Your Inquiry"))
    reply_subject = payload.subject or f"Re: {original_subject}"
    reply_html = _build_reply_html(payload.body, original_subject)

    email_result = {"success": False, "error": "Email service not configured"}
    if is_email_configured():
        email_result = await send_email(
            recipient_email=recipient_email,
            subject=reply_subject,
            content=reply_html,
            recipient_name=submission.get("name", ""),
            contact_external_id=recipient_email,
            content_text=payload.body,
            template_key="contact_reply",
        )
    else:
        logger.warning("Email service not configured — reply not sent")

    # Update submission status
    await db.contact_submissions.update_one(
        {"submission_id": payload.message_id},
        {
            "$set": {
                "status": "replied",
                "replied_at": datetime.now(timezone.utc).isoformat(),
                "replied_by": admin.user_id,
                "reply_body": payload.body,
                "reply_subject": reply_subject,
                "email_sent": email_result.get("success", False),
            }
        },
    )

    return {
        "success": True,
        "email_sent": email_result.get("success", False),
        "email_error": email_result.get("error") if not email_result.get("success") else None,
    }


@router.post("/admin/emails/compose")
async def compose_email(payload: ComposeRequest, req: Request):
    admin = await require_admin(req)

    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service not configured")

    from utils.email_templates import build_admin_outbound_email
    tpl = build_admin_outbound_email(body=payload.body, original_subject=payload.subject)
    result = await send_email(
        recipient_email=payload.recipient_email,
        subject=tpl.subject,
        content=tpl.html,
        contact_external_id=payload.recipient_email,
        content_text=tpl.text,
        template_key="admin_outbound",
        skip_branding=True,
    )

    # Log the sent email
    await db.admin_sent_emails.insert_one(
        {
            "email_id": f"email_{uuid4().hex[:12]}",
            "sent_by": admin.user_id,
            "recipient_email": payload.recipient_email,
            "subject": payload.subject,
            "body": payload.body,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "email_result": result.get("success", False),
        }
    )

    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Failed to send"))

    return {"success": True, "message": "Email sent successfully"}


@router.delete("/admin/emails/{message_id}")
async def delete_email(message_id: str, req: Request):
    await require_admin(req)
    result = await db.contact_submissions.delete_one({"submission_id": message_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"success": True}
