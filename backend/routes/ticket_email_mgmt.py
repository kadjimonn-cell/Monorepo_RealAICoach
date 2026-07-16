"""
Admin-only Ticket Email Management routes.
Allows admins to:
  - Configure the support email address for ticket submissions
  - View/manage user-submitted ticket emails (inbox-style)
  - Set up email templates and auto-replies
  - Configure AI routing rules and re-classify tickets
"""

import logging
import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from routes.db import db, get_current_user
from utils.email_service import render_email_logo, is_email_configured
from utils.field_encryption import decrypt_doc

_TICKET_ENC_FIELDS = ("name", "email", "message")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/ticket-email", tags=["Ticket Email Management"])

COLLECTION = "ticket_email_config"
TEMPLATES_COLLECTION = "ticket_email_templates"
ROUTING_COLLECTION = "ticket_routing_config"

DEFAULT_CONFIG = {
    "support_email": "support@realaicoach.app",
    "reply_to_email": "noreply@realaicoach.app",
    "auto_reply_enabled": True,
    "auto_reply_subject": "We received your ticket - {ticket_id}",
    "auto_reply_body": "Hi {name},\n\nThank you for contacting RealAICoach support. Your ticket {ticket_id} has been created and our team will respond within 24-48 hours.\n\nSubject: {subject}\n\nBest regards,\nRealAICoach Support Team",
    "escalation_enabled": False,
    "escalation_email": "",
    "escalation_after_hours": 48,
    "cc_admins_on_new_ticket": True,
    "signature": "— RealAICoach Support Team",
}

DEFAULT_TEMPLATES = [
    {
        "template_id": "acknowledgment",
        "name": "Ticket Acknowledgment",
        "subject": "Ticket {ticket_id} - We're on it!",
        "body": 'Hi {name},\n\nWe\'ve received your support request regarding "{subject}". Your ticket number is {ticket_id}.\n\nOur team will review and respond within 24-48 hours.\n\n{signature}',
        "trigger": "on_create",
        "active": True,
    },
    {
        "template_id": "resolved",
        "name": "Ticket Resolved",
        "subject": "Ticket {ticket_id} - Resolved",
        "body": 'Hi {name},\n\nYour support ticket {ticket_id} regarding "{subject}" has been resolved.\n\nIf you have further questions, feel free to reply to this email or open a new ticket.\n\n{signature}',
        "trigger": "on_resolve",
        "active": True,
    },
    {
        "template_id": "escalation",
        "name": "Ticket Escalation",
        "subject": "[ESCALATED] Ticket {ticket_id} - {subject}",
        "body": "This ticket has been escalated due to exceeding the response SLA.\n\nTicket: {ticket_id}\nUser: {name} ({email})\nSubject: {subject}\nCreated: {created_at}\n\nPlease review immediately.",
        "trigger": "on_escalate",
        "active": True,
    },
    {
        "template_id": "follow_up",
        "name": "Follow Up",
        "subject": "Following up on Ticket {ticket_id}",
        "body": "Hi {name},\n\nWe're following up on your ticket {ticket_id}. If your issue has been resolved, no action is needed.\n\nIf you still need help, please reply and we'll prioritize your request.\n\n{signature}",
        "trigger": "manual",
        "active": True,
    },
]


async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin access required")
    return user


def _generate_rating_token(ticket_id: str, rating: str) -> str:
    secret = str(os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET is missing or too short for secure rating token generation")
    return hmac.new(secret.encode(), f"{ticket_id}:{rating}".encode(), hashlib.sha256).hexdigest()[:16]


# ─── CONFIG ENDPOINTS ───


@router.get("/config")
async def get_ticket_email_config(request: Request):
    await _require_admin(request)
    stored = await db[COLLECTION].find_one({"_type": "config"}, {"_id": 0})
    config = {**DEFAULT_CONFIG}
    if stored:
        config.update({k: v for k, v in stored.items() if k != "_type"})
    return {"config": config}


@router.put("/config")
async def update_ticket_email_config(request: Request):
    admin = await _require_admin(request)
    body = await request.json()
    allowed = set(DEFAULT_CONFIG.keys())
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No valid config fields provided")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = admin.user_id
    await db[COLLECTION].update_one({"_type": "config"}, {"$set": updates}, upsert=True)
    return {"message": "Config updated", "updated": list(updates.keys())}


# ─── INBOX / TICKET MANAGEMENT ───


@router.get("/inbox")
async def get_ticket_inbox(request: Request, status: str = "all", page: int = 1, limit: int = 25):
    await _require_admin(request)
    query: dict = {}
    if status != "all":
        query["status"] = status

    total = await db.support_tickets.count_documents(query)
    skip = (page - 1) * limit
    tickets = (
        await db.support_tickets.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    )
    for t in tickets:
        decrypt_doc(t, _TICKET_ENC_FIELDS)

    # Also include tickets from the support_submissions collection
    sub_total = await db.support_submissions.count_documents(query)
    submissions = (
        await db.support_submissions.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    # Merge and deduplicate by ticket_id/ticket_number
    seen = set()
    merged = []
    for t in tickets + submissions:
        tid = t.get("ticket_id") or t.get("ticket_number") or ""
        if tid and tid in seen:
            continue
        seen.add(tid)
        created = t.get("created_at", "")
        updated = t.get("updated_at", "")
        merged.append(
            {
                "ticket_id": tid,
                "name": t.get("name") or t.get("user_name", ""),
                "email": t.get("email") or t.get("user_email", ""),
                "subject": t.get("subject", ""),
                "message": t.get("message", ""),
                "category": t.get("category", "general"),
                "status": t.get("status", "open"),
                "priority": t.get("priority", "normal"),
                "admin_notes": t.get("admin_notes", []),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
                "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
                "user_id": t.get("user_id", ""),
                "ai_classification": t.get("ai_classification"),
                "ai_routing": t.get("ai_routing"),
                "ai_tags": t.get("ai_tags", []),
                "assigned_to": t.get("assigned_to", ""),
                "auto_escalated": t.get("auto_escalated", False),
                "escalation_reason": t.get("escalation_reason", ""),
                "csat_rating": t.get("csat_rating"),
                "csat_rated_at": t.get("csat_rated_at"),
            }
        )

    merged.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return {
        "tickets": merged[:limit],
        "total": total + sub_total,
        "page": page,
        "pages": max(1, (total + sub_total + limit - 1) // limit),
    }


@router.put("/ticket/{ticket_id}")
async def update_ticket(request: Request, ticket_id: str):
    admin = await _require_admin(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    updates: dict = {}
    if "status" in body:
        updates["status"] = body["status"]
    if "priority" in body:
        updates["priority"] = body["priority"]

    note_text = body.get("note", "").strip()
    note_push = None
    if note_text:
        note_push = {
            "text": note_text,
            "by": admin.user_id,
            "at": now,
        }

    updates["updated_at"] = now

    # Try both collections
    for coll_name in ["support_tickets", "support_submissions"]:
        coll = db[coll_name]
        id_field = "ticket_id" if coll_name == "support_tickets" else "ticket_number"
        filt = {id_field: ticket_id}
        ops: dict = {"$set": updates}
        if note_push:
            ops["$push"] = {"admin_notes": note_push}
        result = await coll.update_one(filt, ops)
        if result.matched_count > 0:
            # Send status change email notification to user
            if "status" in body:
                try:
                    await _send_status_notification(ticket_id, body["status"], coll_name, id_field)
                except Exception as exc:
                    logger.error(f"Status notification email failed for {ticket_id}: {exc}")
            return {"message": f"Ticket {ticket_id} updated"}

    raise HTTPException(404, "Ticket not found")


async def _send_status_notification(ticket_id: str, new_status: str, coll_name: str, id_field: str):
    """Send email to ticket submitter when status changes."""
    from utils.email_service import send_catalog_template

    ticket = await db[coll_name].find_one({id_field: ticket_id}, {"_id": 0})
    if not ticket:
        return

    user_email = ticket.get("email") or ticket.get("user_email", "")
    user_name = ticket.get("name") or ticket.get("user_name", "User")
    subject_line = ticket.get("subject", "Support Request")

    if not user_email:
        logger.warning(f"No email on ticket {ticket_id}, skipping notification")
        return

    # Get config for signature
    config = await db[COLLECTION].find_one({"_type": "config"}, {"_id": 0})
    signature = (config or {}).get("signature", DEFAULT_CONFIG["signature"])

    # Map status to trigger and find matching template
    trigger_map = {"resolved": "on_resolve", "closed": "on_resolve", "in_progress": "on_create"}
    trigger = trigger_map.get(new_status)

    # Try to load a stored template
    template = None
    if trigger:
        template = await db[TEMPLATES_COLLECTION].find_one({"trigger": trigger, "active": True}, {"_id": 0})

    # Build email content from template or default
    if template:
        template["subject"].replace("{ticket_id}", ticket_id).replace("{subject}", subject_line)
        email_body = (
            template["body"]
            .replace("{name}", user_name)
            .replace("{ticket_id}", ticket_id)
            .replace("{subject}", subject_line)
            .replace("{signature}", signature)
        )
    else:
        status_label = new_status.replace("_", " ").title()
        email_body = f'Hi {user_name},\n\nYour support ticket {ticket_id} regarding "{subject_line}" has been updated to: {status_label}.\n\nIf you have questions, reply to this email or open a new ticket.\n\n{signature}'

    # Rating URLs for resolved/closed
    rate_positive_url = ""
    rate_negative_url = ""
    if new_status in ("resolved", "closed"):
        base_url = os.environ.get("FRONTEND_BASE_URL", "")
        tok_pos = _generate_rating_token(ticket_id, "positive")
        tok_neg = _generate_rating_token(ticket_id, "negative")
        rate_positive_url = f"{base_url}/api/tickets/rate?ticket_id={ticket_id}&rating=positive&token={tok_pos}"
        rate_negative_url = f"{base_url}/api/tickets/rate?ticket_id={ticket_id}&rating=negative&token={tok_neg}"

    # Reply URL for active statuses
    reply_url = ""
    frontend_url = os.environ.get("FRONTEND_BASE_URL", "")
    if new_status not in ("resolved", "closed") and frontend_url:
        reply_url = f"{frontend_url}/my-tickets"

    status_label = new_status.replace("_", " ").title()
    result = await send_catalog_template(
        recipient_email=user_email,
        template_key="ticket_status_update",
        recipient_name=user_name,
        user_name=user_name,
        ticket_id=ticket_id,
        subject_line=subject_line,
        new_status=new_status,
        status_label=status_label,
        email_body=email_body,
        rate_positive_url=rate_positive_url,
        rate_negative_url=rate_negative_url,
        reply_url=reply_url,
    )
    if result.get("success"):
        logger.info(f"Status notification sent to {user_email} for ticket {ticket_id} -> {new_status}")
    else:
        logger.error(f"Status notification failed for {ticket_id}: {result.get('error')}")


@router.post("/ticket/{ticket_id}/reply")
async def reply_to_ticket(request: Request, ticket_id: str):
    """Send an email reply to a ticket submitter."""
    admin = await _require_admin(request)
    body = await request.json()
    reply_text = body.get("message", "").strip()
    if not reply_text:
        raise HTTPException(400, "Message is required")

    # Find the ticket
    ticket = await db.support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not ticket:
        ticket = await db.support_submissions.find_one({"ticket_number": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    user_email = ticket.get("email") or ticket.get("user_email", "")
    user_name = ticket.get("name") or ticket.get("user_name", "User")
    subject = ticket.get("subject", "Support Request")

    if not user_email:
        raise HTTPException(400, "No email address on ticket")

    # Send email via configured provider with a "Reply" CTA link
    email_sent = False
    try:

        config = await db[COLLECTION].find_one({"_type": "config"}, {"_id": 0})
        signature = (config or {}).get("signature", DEFAULT_CONFIG["signature"])
        frontend_url = os.environ.get("FRONTEND_BASE_URL", "")
        reply_link = f"{frontend_url}/my-tickets" if frontend_url else ""

        reply_cta = ""
        if reply_link:
            reply_cta = f"""
            <div style="text-align:center;margin-top:24px;">
              <a href="{reply_link}" style="display:inline-block;padding:12px 32px;background:#3B82F6;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Reply to this message</a>
            </div>
            <p style="text-align:center;color:#94A3B8;font-size:11px;margin-top:10px;">Click above to view and reply to your ticket on the platform</p>"""

        logo_html = render_email_logo(variant="support")
        f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;background:#FAFAFA;">
          <div style="background:#fff;border-radius:16px;padding:32px;border:1px solid #E2E8F0;">
            {logo_html}
            <h2 style="color:#0F172A;font-size:18px;text-align:center;margin:0 0 6px;">Support Reply</h2>
            <p style="color:#64748B;font-size:13px;text-align:center;margin:0 0 24px;">Ticket #{ticket_id} — {subject}</p>
            <div style="background:#F8FAFC;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:16px;margin-bottom:16px;">
              <div style="white-space:pre-line;color:#334155;font-size:14px;line-height:1.7;">{reply_text.replace(chr(10), "<br>")}</div>
            </div>
            <p style="color:#94A3B8;font-size:12px;">{signature}</p>
            {reply_cta}
          </div>
          <p style="text-align:center;color:#CBD5E1;font-size:11px;margin-top:16px;">RealAICoach Support</p>
        </div>"""

        from utils.email_service import send_catalog_template
        agent_name = getattr(admin, "name", "Support Team")
        result = await send_catalog_template(
            recipient_email=user_email,
            template_key="ticket_reply_agent",
            user_name=user_name,
            ticket_id=ticket_id,
            ticket_subject=subject,
            agent_name=agent_name,
            reply_preview=reply_text[:300],
        )
        if result.get("success"):
            email_sent = True
            logger.info(f"Admin reply sent to {user_email} for ticket {ticket_id}")
        else:
            logger.error(f"Email send error for {ticket_id}: {result.get('error')}")
    except Exception as e:
        logger.error(f"Failed to send reply for {ticket_id}: {e}")

    # Record the reply in BOTH admin_notes AND reply_logs so users see it
    now = datetime.now(timezone.utc).isoformat()
    note = {"text": f"[EMAIL REPLY] {reply_text}", "by": admin.user_id, "at": now}
    reply_log_entry = {
        "from": getattr(admin, "email", admin.user_id),
        "from_name": getattr(admin, "name", "Support Team"),
        "message": reply_text,
        "role": "admin",
        "at": now,
    }
    history_entry = {
        "action": "admin_reply",
        "note": reply_text[:100],
        "by": admin.user_id,
        "by_name": getattr(admin, "name", "Support Team"),
        "at": now,
    }
    for coll_name in ["support_tickets", "support_submissions"]:
        id_field = "ticket_id" if coll_name == "support_tickets" else "ticket_number"
        await db[coll_name].update_one(
            {id_field: ticket_id},
            {
                "$push": {
                    "admin_notes": note,
                    "reply_logs": reply_log_entry,
                    "history": history_entry,
                },
                "$set": {"updated_at": now, "status": "in_progress"},
            },
        )

    # Send in-app notification to user
    user_id = ticket.get("user_id", "")
    if user_id:
        try:
            from routes.notification_engine import emit_notification

            await emit_notification(
                user_id=user_id,
                notif_type="ticket_admin_reply",
                title=f"Reply on ticket {ticket_id}",
                body=reply_text[:100],
                action_url="/my-tickets",
                metadata={"ticket_id": ticket_id},
            )
        except Exception as e:
            logger.error(f"Notification failed for user {user_id}: {e}")

    return {"message": f"Reply sent to {user_email}", "email_sent": email_sent}


# ─── TEMPLATE ENDPOINTS ───


@router.get("/templates")
async def get_templates(request: Request):
    await _require_admin(request)
    stored = await db[TEMPLATES_COLLECTION].find({}, {"_id": 0}).to_list(50)
    if not stored:
        return {"templates": DEFAULT_TEMPLATES}
    return {"templates": stored}


@router.put("/template/{template_id}")
async def update_template(request: Request, template_id: str):
    admin = await _require_admin(request)
    body = await request.json()
    allowed = {"name", "subject", "body", "trigger", "active"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No valid template fields provided")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = admin.user_id

    result = await db[TEMPLATES_COLLECTION].update_one({"template_id": template_id}, {"$set": updates}, upsert=True)
    # Seed if first time
    if result.upserted_id:
        tmpl = next((t for t in DEFAULT_TEMPLATES if t["template_id"] == template_id), None)
        if tmpl:
            merged = {**tmpl, **updates}
            await db[TEMPLATES_COLLECTION].replace_one({"template_id": template_id}, merged)

    return {"message": f"Template '{template_id}' updated"}


@router.post("/template")
async def create_template(request: Request):
    admin = await _require_admin(request)
    body = await request.json()
    required = {"template_id", "name", "subject", "body", "trigger"}
    if not required.issubset(body.keys()):
        raise HTTPException(400, f"Missing fields: {required - set(body.keys())}")

    existing = await db[TEMPLATES_COLLECTION].find_one({"template_id": body["template_id"]})
    if existing:
        raise HTTPException(409, "Template ID already exists")

    doc = {
        "template_id": body["template_id"],
        "name": body["name"],
        "subject": body["subject"],
        "body": body["body"],
        "trigger": body["trigger"],
        "active": body.get("active", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin.user_id,
    }
    await db[TEMPLATES_COLLECTION].insert_one(doc)
    doc.pop("_id", None)
    return {"message": "Template created", "template": doc}


# ─── STATS ───


@router.get("/stats")
async def get_ticket_stats(request: Request):
    await _require_admin(request)
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    status_counts_tickets = {r["_id"]: r["count"] async for r in db.support_tickets.aggregate(pipeline)}
    status_counts_subs = {r["_id"]: r["count"] async for r in db.support_submissions.aggregate(pipeline)}

    # Merge
    all_statuses = set(list(status_counts_tickets.keys()) + list(status_counts_subs.keys()))
    merged = {}
    for s in all_statuses:
        merged[s] = status_counts_tickets.get(s, 0) + status_counts_subs.get(s, 0)

    total = sum(merged.values())
    open_count = merged.get("open", 0) + merged.get("new", 0)
    in_progress = merged.get("in_progress", 0) + merged.get("in-progress", 0)
    resolved = merged.get("resolved", 0) + merged.get("closed", 0)

    return {
        "total": total,
        "open": open_count,
        "in_progress": in_progress,
        "resolved": resolved,
        "by_status": merged,
    }


# ─── CSAT STATS ───


@router.get("/csat-stats")
async def get_csat_stats(request: Request):
    await _require_admin(request)
    pipeline = [
        {"$match": {"csat_rating": {"$exists": True}}},
        {"$group": {"_id": "$csat_rating", "count": {"$sum": 1}}},
    ]
    results: dict = {}
    for coll_name in ["support_tickets", "support_submissions"]:
        async for doc in db[coll_name].aggregate(pipeline):
            results[doc["_id"]] = results.get(doc["_id"], 0) + doc["count"]
    positive = results.get("positive", 0)
    negative = results.get("negative", 0)
    total = positive + negative
    score = round((positive / total) * 100) if total > 0 else 0
    return {
        "total_ratings": total,
        "positive": positive,
        "negative": negative,
        "satisfaction_score": score,
    }


# ─── EMAIL HEALTH CHECK ───


@router.get("/email-health")
async def check_email_health(request: Request):
    """Admin endpoint: checks Resend delivery health from internal email logs."""
    await _require_admin(request)
    try:
        configured = is_email_configured()
        now = datetime.now(timezone.utc)
        since_24h = (now - timedelta(hours=24)).isoformat()
        since_1h = (now - timedelta(hours=1)).isoformat()

        sent_24h = await db.email_logs.count_documents({"status": "sent", "created_at": {"$gte": since_24h}})
        failed_24h = await db.email_logs.count_documents({"status": "failed", "created_at": {"$gte": since_24h}})
        sent_1h = await db.email_logs.count_documents({"status": "sent", "created_at": {"$gte": since_1h}})
        failed_1h = await db.email_logs.count_documents({"status": "failed", "created_at": {"$gte": since_1h}})
        total_24h = sent_24h + failed_24h

        latest_failed = await db.email_logs.find_one(
            {"status": "failed", "created_at": {"$gte": since_24h}},
            {"_id": 0, "error": 1, "created_at": 1, "email_type": 1},
            sort=[("created_at", -1)],
        ) or {}

        if not configured:
            health = "down"
        elif total_24h == 0:
            health = "healthy"
        else:
            failure_ratio = failed_24h / max(total_24h, 1)
            if failure_ratio < 0.05:
                health = "healthy"
            elif failure_ratio < 0.25:
                health = "degraded"
            else:
                health = "down"

        return {
            "provider": "resend",
            "configured": configured,
            "health": health,
            "window_24h": {
                "total": total_24h,
                "sent": sent_24h,
                "failed": failed_24h,
            },
            "window_1h": {
                "sent": sent_1h,
                "failed": failed_1h,
            },
            "last_error": (latest_failed.get("error") or "")[:240],
            "last_error_at": latest_failed.get("created_at"),
            "last_error_type": latest_failed.get("email_type"),
        }
    except Exception as exc:
        return {"health": "unknown", "error": str(exc)}


# ─── ROUTING CONFIG ───

DEFAULT_ROUTING_RULES = {
    "billing": {"assigned_to": "support@realaicoach.app", "team": "Support Team"},
    "technical": {"assigned_to": "support@realaicoach.app", "team": "Support Team"},
    "account": {"assigned_to": "support@realaicoach.app", "team": "Support Team"},
    "feature_request": {"assigned_to": "support@realaicoach.app", "team": "Support Team"},
    "bug_report": {"assigned_to": "support@realaicoach.app", "team": "Support Team"},
    "general": {"assigned_to": "support@realaicoach.app", "team": "Support Team"},
}


@router.get("/routing")
async def get_routing_config(request: Request):
    await _require_admin(request)
    stored = await db[ROUTING_COLLECTION].find_one({"_type": "routing"}, {"_id": 0})
    rules = {**DEFAULT_ROUTING_RULES}
    if stored and stored.get("rules"):
        rules.update(stored["rules"])
    return {"rules": rules}


@router.put("/routing")
async def update_routing_config(request: Request):
    admin = await _require_admin(request)
    body = await request.json()
    rules = body.get("rules", {})
    if not isinstance(rules, dict):
        raise HTTPException(400, "rules must be a dict mapping topic to {assigned_to, team}")
    await db[ROUTING_COLLECTION].update_one(
        {"_type": "routing"},
        {"$set": {"rules": rules, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": admin.user_id}},
        upsert=True,
    )
    return {"message": "Routing config updated"}


# ─── AI RE-CLASSIFY ───


@router.post("/reclassify/{ticket_id}")
async def reclassify_ticket(request: Request, ticket_id: str):
    """Re-run AI classification on a specific ticket."""
    await _require_admin(request)

    # Find ticket
    ticket = await db.support_tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
    coll_name = "support_tickets"
    id_field = "ticket_id"
    if not ticket:
        ticket = await db.support_submissions.find_one({"ticket_number": ticket_id}, {"_id": 0})
        coll_name = "support_submissions"
        id_field = "ticket_number"
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    subject = ticket.get("subject", "")
    message = ticket.get("message", "")
    user_name = ticket.get("name") or ticket.get("user_name", "User")

    from services.ai_ticket_router import classify_ticket, route_ticket

    classification = await classify_ticket(subject, message, user_name)
    routing_cfg = await db[ROUTING_COLLECTION].find_one({"_type": "routing"}, {"_id": 0})
    rules = (routing_cfg or {}).get("rules", {})
    routing = await route_ticket(classification.get("topic", "general"), rules)

    update_fields = {
        "ai_classification": classification,
        "ai_routing": routing,
        "category": classification.get("topic", "general"),
        "priority": classification.get("priority", "medium"),
        "ai_tags": classification.get("tags", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if routing.get("assigned_to"):
        update_fields["assigned_to"] = routing["assigned_to"]

    # Auto-escalate on negative sentiment
    sentiment = classification.get("sentiment", {})
    if sentiment.get("auto_escalate"):
        update_fields["priority"] = "critical"
        update_fields["auto_escalated"] = True
        update_fields["escalation_reason"] = (
            f"Customer mood: {sentiment.get('mood', 'unknown')} (frustration: {sentiment.get('frustration_level', '?')}/10)"
        )

    await db[coll_name].update_one({id_field: ticket_id}, {"$set": update_fields})

    return {
        "message": f"Ticket {ticket_id} reclassified",
        "classification": classification,
        "routing": routing,
    }
