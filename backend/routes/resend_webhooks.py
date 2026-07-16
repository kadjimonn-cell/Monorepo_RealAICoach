"""Resend Webhook Receiver — Tracks email delivery events in real-time.

Receives webhook POSTs from Resend for events like email.delivered,
email.bounced, email.opened, email.complained. Verifies signature via
svix/standardwebhooks, stores events, and updates email_logs status.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
import re

from routes.db import db

logger = logging.getLogger("routes.resend_webhooks")
router = APIRouter(prefix="/webhooks", tags=["Resend Webhooks"])

RESEND_WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")

# Map Resend event types to our internal status
EVENT_STATUS_MAP = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.opened": "opened",
    "email.clicked": "clicked",
}


def _verify_webhook(payload: bytes, headers: dict) -> bool:
    """Verify Resend webhook signature using standardwebhooks."""
    if not RESEND_WEBHOOK_SECRET:
        logger.warning("RESEND_WEBHOOK_SECRET not set — skipping verification")
        return True

    svix_id = headers.get("svix-id", headers.get("webhook-id", ""))
    svix_ts = headers.get("svix-timestamp", headers.get("webhook-timestamp", ""))
    svix_sig = headers.get("svix-signature", headers.get("webhook-signature", ""))

    # If no svix headers at all, skip verification (non-Resend caller)
    if not svix_id and not svix_ts and not svix_sig:
        logger.info("No svix headers present — skipping verification")
        return True

    try:
        from standardwebhooks.webhooks import Webhook

        wh = Webhook(RESEND_WEBHOOK_SECRET)
        wh.verify(
            payload,
            {
                "webhook-id": svix_id,
                "webhook-timestamp": svix_ts,
                "webhook-signature": svix_sig,
            },
        )
        return True
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        return False


@router.post("/resend")
async def handle_resend_webhook(request: Request):
    """Receive and process Resend delivery webhooks."""
    return {"status": "ok"}
    body = await request.body()
    headers = dict(request.headers)

    # Verify signature
    if RESEND_WEBHOOK_SECRET and not _verify_webhook(body, headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("type", "")
    event_data = payload.get("data", {})
    created_at = payload.get("created_at", datetime.now(timezone.utc).isoformat())

    # Extract key fields from Resend event
    email_id = event_data.get("email_id", "")
    to_list = event_data.get("to", [])
    recipient = to_list[0] if to_list else ""
    subject = event_data.get("subject", "")
    from_addr = event_data.get("from", "")

    internal_status = EVENT_STATUS_MAP.get(event_type, event_type)

    # Store the raw delivery event
    event_doc = {
        "event_type": event_type,
        "internal_status": internal_status,
        "email_id": email_id,
        "recipient": recipient,
        "subject": subject,
        "from_addr": from_addr,
        "raw_data": event_data,
        "created_at": created_at,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_delivery_events.insert_one(event_doc)

    # Update email_logs if we can match by message_id
    if email_id:
        update_fields = {
            "delivery_status": internal_status,
            "delivery_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if internal_status == "delivered":
            update_fields["delivered_at"] = created_at
        elif internal_status == "bounced":
            update_fields["bounced_at"] = created_at
            update_fields["bounce_reason"] = event_data.get("bounce", {}).get("message", "")
        elif internal_status == "opened":
            update_fields["opened_at"] = created_at

        await db.email_logs.update_many(
            {"message_id": email_id},
            {"$set": update_fields},
        )

    logger.info(f"[Resend Webhook] {event_type} for {recipient} (email_id={email_id})")

    # ── Careers-specific fan-out → careers_tracker_events ───────────────
    # Every careers email send attaches a `tags[application_id]` entry. We
    # mirror matching open/click/delivered/bounced events into a lean
    # `careers_tracker_events` collection so the admin applicant drawer's
    # "Engagement" strip can render without joining against email_logs.
    _CAREERS_TEMPLATES = {
        "career_confirmation", "career_status_update",
        "career_status_received", "career_status_under_review",
        "career_status_interview", "career_status_offer",
        "career_status_hired", "career_status_rejected",
        "career_applicant_withdraw_notice",
    }
    template_key = ""
    application_id = ""
    tags_raw = event_data.get("tags", [])
    if isinstance(tags_raw, list):
        for t in tags_raw:
            if isinstance(t, dict):
                if t.get("name") == "template":
                    template_key = t.get("value", "") or ""
                elif t.get("name") == "application_id":
                    application_id = t.get("value", "") or ""
    if template_key in _CAREERS_TEMPLATES and application_id:
        try:
            await db["careers_tracker_events"].insert_one({
                "application_id": application_id,
                "template": template_key,
                "event_type": internal_status,
                "email_id": email_id,
                "to": [recipient] if recipient else [],
                "subject": subject,
                "created_at_provider": created_at,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "click_link": (event_data.get("click") or {}).get("link") if isinstance(event_data.get("click"), dict) else None,
            })
        except Exception as _e:
            logger.warning(f"[Resend Webhook] careers fan-out failed: {_e}")

    # Reactive rule: auto-revoke pending platform-employee invitations whose email bounced
    # or was flagged as spam/complaint. Gives admins a red pill + audit entry they can act on.
    if email_id and internal_status in ("bounced", "complained"):
        try:
            inv = await db.platform_employee_invitations.find_one(
                {"last_email_id": email_id, "status": "pending"},
                {"_id": 0, "invitation_id": 1, "email": 1, "platform_role": 1, "invited_by_user_id": 1, "invited_by_email": 1},
            )
            if inv:
                revoke_reason = "email_bounced" if internal_status == "bounced" else "email_complained"
                bounce_detail = ""
                if internal_status == "bounced":
                    bounce_detail = (event_data.get("bounce") or {}).get("message", "")

                await db.platform_employee_invitations.update_one(
                    {"invitation_id": inv["invitation_id"]},
                    {"$set": {
                        "status": "revoked",
                        "revoked_at": datetime.now(timezone.utc).isoformat(),
                        "revoked_by_email": "system:resend_webhook",
                        "revoke_reason": revoke_reason,
                        "revoke_detail": bounce_detail,
                    }},
                )

                try:
                    await db.employee_audit_log.insert_one({
                        "audit_id": f"aud_{datetime.now(timezone.utc).timestamp()}",
                        "actor_user_id": "system",
                        "actor_email": "system:resend_webhook",
                        "action": "invitation_auto_revoked",
                        "target_user_id": None,
                        "target_email": inv["email"],
                        "details": {
                            "invitation_id": inv["invitation_id"],
                            "platform_role": inv.get("platform_role"),
                            "invited_by_email": inv.get("invited_by_email"),
                            "reason": revoke_reason,
                            "bounce_detail": bounce_detail,
                            "event_type": event_type,
                            "email_id": email_id,
                        },
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as audit_exc:
                    logger.warning(f"[Resend Webhook] audit-log insert failed: {audit_exc}")

                logger.warning(
                    f"[Resend Webhook] auto-revoked invitation {inv['invitation_id']} "
                    f"({inv['email']}) — reason={revoke_reason}"
                )
        except Exception as auto_exc:
            logger.error(f"[Resend Webhook] auto-revoke failed: {auto_exc}")

    return {"status": "ok"}


@router.get("/resend/events")
async def get_delivery_events(
    limit: int = 50,
    event_type: Optional[str] = None,
    email: Optional[str] = None,
):
    """Fetch recent delivery events for the dashboard."""
    query: dict = {}
    if event_type:
        query["event_type"] = event_type
    if email:
        query["recipient"] = {"$regex": re.escape(str(email)), "$options": "i"}

    events = []
    cursor = db.email_delivery_events.find(query, {"_id": 0, "raw_data": 0}).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        events.append(doc)

    return {"events": events, "total": len(events)}


@router.get("/resend/stats")
async def get_delivery_stats(days: int = 30):
    """Aggregate delivery event statistics."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$internal_status", "count": {"$sum": 1}}},
    ]
    breakdown = {}
    async for doc in db.email_delivery_events.aggregate(pipeline):
        breakdown[doc["_id"]] = doc["count"]

    total = sum(breakdown.values())
    delivered = breakdown.get("delivered", 0)
    bounced = breakdown.get("bounced", 0)
    opened = breakdown.get("opened", 0)
    complained = breakdown.get("complained", 0)

    return {
        "window_days": days,
        "total_events": total,
        "delivered": delivered,
        "bounced": bounced,
        "opened": opened,
        "complained": complained,
        "delivery_rate": round((delivered / max(total, 1)) * 100, 1),
        "open_rate": round((opened / max(delivered, 1)) * 100, 1),
        "bounce_rate": round((bounced / max(total, 1)) * 100, 1),
        "breakdown": breakdown,
    }
