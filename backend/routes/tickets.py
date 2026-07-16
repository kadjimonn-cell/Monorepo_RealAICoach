"""User-facing Ticket Support System — Submit, track, reply, with real-time notifications."""

import os
import hmac
import hashlib
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import uuid
import mimetypes

from .db import db, get_current_user, logger
from utils.file_security_service import enforce_file_security

router = APIRouter(prefix="/tickets")

SLA_HOURS_BY_PRIORITY = {
    "low": 24,
    "medium": 24,
    "high": 12,
    "urgent": 4,
    "critical": 4,
}

ATTACHMENT_DIR = "/app/backend/media/ticket_attachments"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ATTACHMENTS = 5
ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".csv",
    ".rtf",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".mp3",
    ".wav",
    ".ogg",
    ".aac",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
}

ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/svg+xml",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/rtf",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/aac",
    "application/zip",
    "application/vnd.rar",
    "application/x-7z-compressed",
    "application/x-tar",
    "application/gzip",
}


def _gen_ticket_number() -> str:
    """Generate a human-readable ticket number: TKT-YYYYMMDD-XXXXXXXX"""
    return f"TKT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


class TicketCreate(BaseModel):
    subject: str
    message: str
    category: str = "general"
    priority: str = "medium"
    attachment_ids: List[str] = []


class TicketReply(BaseModel):
    message: str
    attachment_ids: List[str] = []


class TicketAIDraftRequest(BaseModel):
    subject: str = ""
    message: str = ""
    category: str = "general"
    priority: str = "medium"
    tone: str = "professional"
    mode: str = "draft"  # draft | rewrite


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _compute_sla(ticket: Dict[str, Any]) -> Dict[str, Any]:
    priority = str(ticket.get("priority") or "medium").lower()
    target_hours = SLA_HOURS_BY_PRIORITY.get(priority, 24)
    created_at = _parse_iso_dt(ticket.get("created_at"))
    status = str(ticket.get("status") or "open").lower()

    if not created_at:
        return {
            "target_hours": target_hours,
            "elapsed_hours": 0.0,
            "remaining_hours": target_hours,
            "breached": False,
            "at_risk": False,
            "state": "unknown",
        }

    elapsed_hours = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600)
    if status in {"resolved", "closed"}:
        state = "closed"
        breached = False
        at_risk = False
    else:
        breached = elapsed_hours > target_hours
        at_risk = (elapsed_hours / max(1, target_hours)) >= 0.75 and not breached
        state = "breached" if breached else "at_risk" if at_risk else "healthy"

    return {
        "target_hours": target_hours,
        "elapsed_hours": round(elapsed_hours, 2),
        "remaining_hours": max(0.0, round(target_hours - elapsed_hours, 2)),
        "breached": breached,
        "at_risk": at_risk,
        "state": state,
    }


def _compute_unread(ticket: Dict[str, Any]) -> Dict[str, Any]:
    last_user_read_at = _parse_iso_dt(ticket.get("last_user_read_at"))
    created_at = _parse_iso_dt(ticket.get("created_at")) or datetime.now(timezone.utc)
    threshold = last_user_read_at or created_at

    unread_count = 0
    last_admin_reply_at = None
    for reply in ticket.get("reply_logs") or []:
        if str(reply.get("role") or "") != "admin":
            continue
        at = _parse_iso_dt(reply.get("at"))
        if not at:
            continue
        if not last_admin_reply_at or at > last_admin_reply_at:
            last_admin_reply_at = at
        if at > threshold:
            unread_count += 1

    return {
        "unread_count": unread_count,
        "has_unread": unread_count > 0,
        "last_admin_reply_at": last_admin_reply_at.isoformat() if last_admin_reply_at else None,
        "last_user_read_at": threshold.isoformat(),
    }


def _normalize_ticket_for_user(ticket: Dict[str, Any]) -> Dict[str, Any]:
    doc = {**(ticket or {})}
    doc.pop("_id", None)
    unread = _compute_unread(doc)
    sla = _compute_sla(doc)
    doc["unread_count"] = unread["unread_count"]
    doc["has_unread"] = unread["has_unread"]
    doc["last_admin_reply_at"] = unread["last_admin_reply_at"]
    doc["last_user_read_at"] = unread["last_user_read_at"]
    doc["sla"] = sla
    return doc


# ── User Endpoints ──


@router.post("/upload-attachment")
async def upload_ticket_attachment(request: Request, file: UploadFile = File(...)):
    """Upload a file attachment for use in a ticket. Returns attachment metadata."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_SIZE // (1024 * 1024)}MB limit")

    try:
        security_scan = enforce_file_security(
            content=content,
            claimed_content_type=str(file.content_type or "application/octet-stream"),
            allowed_content_types=ALLOWED_CONTENT_TYPES,
            allow_unrecognized_signatures=True,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Attachment failed security scan")

    file_id = f"att_{uuid.uuid4().hex[:12]}"
    safe_name = f"{file_id}{ext}"
    file_path = os.path.join(ATTACHMENT_DIR, safe_name)

    os.makedirs(ATTACHMENT_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)

    mime_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    attachment_meta = {
        "file_id": file_id,
        "original_name": file.filename,
        "stored_name": safe_name,
        "size": len(content),
        "mime_type": mime_type,
        "security_scan": security_scan,
        "uploaded_by": user.user_id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ticket_attachments.insert_one(attachment_meta)

    return {
        "file_id": file_id,
        "original_name": file.filename,
        "size": len(content),
        "mime_type": mime_type,
    }


@router.get("/attachment/{file_id}")
async def serve_ticket_attachment(file_id: str, request: Request):
    """Serve a ticket attachment file."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    meta = await db.ticket_attachments.find_one({"file_id": file_id}, {"_id": 0})
    if not meta:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = os.path.join(ATTACHMENT_DIR, meta["stored_name"])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        file_path, media_type=meta.get("mime_type", "application/octet-stream"), filename=meta["original_name"]
    )


@router.post("/submit")
async def submit_ticket(payload: TicketCreate, request: Request):
    """Submit a new support ticket. Returns ticket number for tracking."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ticket_number = _gen_ticket_number()
    submission_id = f"sub_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Resolve attachment metadata
    attachments = []
    for att_id in payload.attachment_ids[:MAX_ATTACHMENTS]:
        att = await db.ticket_attachments.find_one({"file_id": att_id, "uploaded_by": user.user_id}, {"_id": 0})
        if att:
            attachments.append(
                {
                    "file_id": att["file_id"],
                    "original_name": att["original_name"],
                    "size": att["size"],
                    "mime_type": att["mime_type"],
                }
            )

    ticket = {
        "submission_id": submission_id,
        "ticket_number": ticket_number,
        "user_id": user.user_id,
        "user_email": getattr(user, "email", ""),
        "user_name": getattr(user, "name", ""),
        "subject": payload.subject,
        "message": payload.message,
        "category": payload.category,
        "priority": payload.priority,
        "status": "open",
        "assigned_to": None,
        "attachments": attachments,
        "reply_logs": [],
        "history": [
            {
                "action": "created",
                "note": "Ticket submitted by user",
                "by": user.user_id,
                "by_name": getattr(user, "name", "User"),
                "at": now_iso,
            }
        ],
        "resolved_at": None,
        "last_user_read_at": now_iso,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    await db.support_submissions.insert_one(ticket)
    ticket.pop("_id", None)

    # Emit notification to user
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user.user_id,
            notif_type="ticket_created",
            title="Ticket Created",
            body=f"Your support ticket {ticket_number} has been created. We'll respond within 24-48 hours.",
            action_url="/my-tickets",
            metadata={"ticket_number": ticket_number},
        )
    except Exception as e:
        logger.error(f"Ticket notification failed: {e}")

    # Notify admins
    try:
        from routes.notification_engine import emit_notification

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(10)
        for admin in admins:
            await emit_notification(
                user_id=admin["user_id"],
                notif_type="new_ticket",
                title=f"New Ticket: {payload.subject[:50]}",
                body=f"Ticket {ticket_number} from {getattr(user, 'name', 'User')} ({getattr(user, 'email', '')})",
                action_url="/admin-console",
                metadata={"ticket_number": ticket_number, "submission_id": submission_id},
            )
    except Exception as e:
        logger.error(f"Admin ticket notification failed: {e}")

    # Send confirmation email
    try:
        from utils.email_service import is_email_configured
        from utils.email_service import render_email_logo

        if is_email_configured():
            logo_html = render_email_logo(variant="support")
            f"""
            <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;background:#0F1117;color:#E5E7EB;border-radius:16px;overflow:hidden;">
              <div style="background:linear-gradient(135deg,#3B82F6,#6366F1);padding:28px;text-align:center;">
                {logo_html}
                <div style="font-size:22px;font-weight:800;color:#fff;">Ticket Received</div>
                <div style="font-size:14px;color:rgba(255,255,255,0.85);margin-top:8px;">Your ticket number: <strong>{ticket_number}</strong></div>
              </div>
              <div style="padding:24px;">
                <p style="color:#D1D5DB;font-size:14px;line-height:1.6;margin:0 0 12px;">Hi {getattr(user, "name", "there")},</p>
                <p style="color:#D1D5DB;font-size:14px;line-height:1.6;margin:0 0 12px;">We've received your support request:</p>
                <div style="background:#1F2937;border-radius:10px;padding:16px;margin:12px 0;">
                  <p style="color:#fff;font-weight:600;margin:0 0 6px;">{payload.subject}</p>
                  <p style="color:#9CA3AF;font-size:13px;margin:0;">{payload.message[:200]}{"..." if len(payload.message) > 200 else ""}</p>
                </div>
                <p style="color:#D1D5DB;font-size:14px;line-height:1.6;margin:12px 0;">Our team will respond within 24-48 hours. You can track your ticket anytime from your dashboard.</p>
                <p style="color:#6B7280;font-size:12px;text-align:center;margin-top:24px;">RealAICoach Support</p>
              </div>
            </div>"""
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=getattr(user, "email", ""),
                template_key="ticket_created",
                recipient_name=getattr(user, "name", "User"),
                user_name=getattr(user, "name", "there"),
                ticket_id=ticket_number,
            )
    except Exception as e:
        logger.error(f"Ticket confirmation email failed: {e}")

    # --- AI Auto-Support + Smart Routing ---
    try:
        from services.ai_ticket_router import classify_ticket, route_ticket
        import asyncio

        async def _ai_classify_and_route(sub_id: str, subj: str, msg: str, uname: str):
            try:
                classification = await classify_ticket(subj, msg, uname)
                routing_cfg = await db.ticket_routing_config.find_one({"_type": "routing"}, {"_id": 0})
                rules = (routing_cfg or {}).get("rules", {})
                routing = await route_ticket(classification.get("topic", "general"), rules)
                update_fields = {
                    "ai_classification": classification,
                    "ai_routing": routing,
                }
                if classification.get("topic"):
                    update_fields["category"] = classification["topic"]
                if classification.get("priority"):
                    update_fields["priority"] = classification["priority"]
                if classification.get("tags"):
                    update_fields["ai_tags"] = classification["tags"]
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
                    logger.warning(
                        f"Auto-escalating ticket {sub_id}: mood={sentiment.get('mood')}, frustration={sentiment.get('frustration_level')}"
                    )

                await db.support_submissions.update_one({"submission_id": sub_id}, {"$set": update_fields})
                logger.info(
                    f"AI classified ticket {sub_id}: topic={classification.get('topic')}, priority={classification.get('priority')}"
                )

                # ── Auto-assign to best available agent ──
                try:
                    assignment_cfg = await db.ticket_assignment_config.find_one(
                        {"_type": "assignment_rules"}, {"_id": 0}
                    )
                    if assignment_cfg and assignment_cfg.get("enabled"):
                        topic = classification.get("topic", "general")
                        strategy = assignment_cfg.get("strategy", "round_robin")
                        agents = await db.support_agents.find({"is_available": True}, {"_id": 0}).to_list(100)
                        if agents:
                            from routes.admin_management import _find_best_agent

                            best = await _find_best_agent(agents, topic, strategy)
                            if best:
                                now_iso_assign = datetime.now(timezone.utc).isoformat()
                                await db.support_submissions.update_one(
                                    {"submission_id": sub_id},
                                    {
                                        "$set": {
                                            "assigned_to": best["email"],
                                            "assigned_agent_name": best.get("name", ""),
                                            "assignment_type": "auto",
                                            "assigned_at": now_iso_assign,
                                        },
                                        "$push": {
                                            "history": {
                                                "action": "auto_assigned",
                                                "note": f"Auto-assigned to {best.get('name', best['email'])} (topic: {topic})",
                                                "by": "system",
                                                "by_name": "AI Assignment Engine",
                                                "at": now_iso_assign,
                                            }
                                        },
                                    },
                                )
                                logger.info(f"Auto-assigned ticket {sub_id} to {best['email']}")
                except Exception as assign_err:
                    logger.error(f"Auto-assignment failed for {sub_id}: {assign_err}")

            except Exception as exc:
                logger.error(f"AI classify/route failed for {sub_id}: {exc}")

        asyncio.create_task(
            _ai_classify_and_route(submission_id, payload.subject, payload.message, getattr(user, "name", "User"))
        )
    except Exception as e:
        logger.error(f"AI classify trigger failed: {e}")

    # --- AI Auto-Support: attempt auto-respond on new ticket ---
    # (Fire-and-forget; don't block ticket creation)
    try:
        from routes.ai_auto_support import _auto_respond_internal
        import asyncio

        asyncio.create_task(_auto_respond_internal(submission_id, user.user_id))
    except Exception as e:
        logger.error(f"AI auto-respond trigger failed: {e}")

    return {
        "success": True,
        "ticket_number": ticket_number,
        "submission_id": submission_id,
        "status": "open",
        "message": f"Ticket {ticket_number} created. We'll respond within 24-48 hours.",
    }


@router.get("/my-tickets")
async def get_my_tickets(
    request: Request,
    status: str = "all",
    priority: str = "all",
    category: str = "all",
    search: str = "",
    sla_state: str = "all",
    date_from: str = "",
    date_to: str = "",
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    page: int = 1,
    limit: int = 20,
):
    """Get all tickets for the current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    query = {"user_id": user.user_id}
    if status != "all":
        query["status"] = status
    if priority != "all":
        query["priority"] = priority
    if category != "all":
        query["category"] = category

    if search.strip():
        q = search.strip()
        query["$or"] = [
            {"ticket_number": {"$regex": q, "$options": "i"}},
            {"subject": {"$regex": q, "$options": "i"}},
            {"message": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
        ]

    if date_from or date_to:
        created_filters: Dict[str, Any] = {}
        parsed_from = _parse_iso_dt(date_from)
        parsed_to = _parse_iso_dt(date_to)
        if parsed_from:
            created_filters["$gte"] = parsed_from.isoformat()
        if parsed_to:
            created_filters["$lte"] = parsed_to.isoformat()
        if created_filters:
            query["created_at"] = created_filters

    safe_limit = max(1, min(limit, 200))
    safe_page = max(1, page)

    sort_field_map = {
        "created_at": "created_at",
        "updated_at": "updated_at",
        "priority": "priority",
        "status": "status",
    }
    sort_field = sort_field_map.get(sort_by, "updated_at")
    sort_dir = -1 if str(sort_order).lower() == "desc" else 1

    total = await db.support_submissions.count_documents(query)
    if sla_state == "all":
        tickets = (
            await db.support_submissions.find(query, {"_id": 0})
            .sort(sort_field, sort_dir)
            .skip((safe_page - 1) * safe_limit)
            .limit(safe_limit)
            .to_list(safe_limit)
        )
        normalized = [_normalize_ticket_for_user(ticket) for ticket in tickets]
        filtered_total = total
    else:
        all_candidates = await db.support_submissions.find(query, {"_id": 0}).sort(sort_field, sort_dir).limit(5000).to_list(5000)
        normalized_all = [_normalize_ticket_for_user(ticket) for ticket in all_candidates]
        filtered = [ticket for ticket in normalized_all if str(ticket.get("sla", {}).get("state")) == sla_state]
        filtered_total = len(filtered)
        start = (safe_page - 1) * safe_limit
        end = start + safe_limit
        normalized = filtered[start:end]

    return {
        "tickets": normalized,
        "total": filtered_total,
        "page": safe_page,
        "pages": max(1, (filtered_total + safe_limit - 1) // safe_limit),
        "applied_filters": {
            "status": status,
            "priority": priority,
            "category": category,
            "search": search,
            "sla_state": sla_state,
            "date_from": date_from,
            "date_to": date_to,
            "sort_by": sort_field,
            "sort_order": "desc" if sort_dir < 0 else "asc",
        },
    }


@router.get("/my-tickets/analytics")
async def get_my_tickets_analytics(
    request: Request,
    range_days: int = Query(default=90, ge=7, le=365),
):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tickets = await db.support_submissions.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "status": 1,
            "priority": 1,
            "category": 1,
            "created_at": 1,
            "updated_at": 1,
            "resolved_at": 1,
            "reply_logs": 1,
            "last_user_read_at": 1,
        },
    ).to_list(2000)

    normalized = [_normalize_ticket_for_user(ticket) for ticket in tickets]
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (range_days * 24 * 3600)
    in_range = []
    for ticket in normalized:
        created = _parse_iso_dt(ticket.get("created_at"))
        if created and created.timestamp() >= cutoff:
            in_range.append(ticket)

    status_counts: Dict[str, int] = {}
    priority_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    unread_total = 0
    sla_breached = 0
    resolution_hours: List[float] = []

    for ticket in in_range:
        status = str(ticket.get("status") or "unknown")
        priority_key = str(ticket.get("priority") or "unknown")
        category_key = str(ticket.get("category") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        priority_counts[priority_key] = priority_counts.get(priority_key, 0) + 1
        category_counts[category_key] = category_counts.get(category_key, 0) + 1

        unread_total += int(ticket.get("unread_count") or 0)
        if ticket.get("sla", {}).get("state") == "breached":
            sla_breached += 1

        if status in {"resolved", "closed"}:
            created = _parse_iso_dt(ticket.get("created_at"))
            resolved = _parse_iso_dt(ticket.get("resolved_at")) or _parse_iso_dt(ticket.get("updated_at"))
            if created and resolved and resolved >= created:
                resolution_hours.append((resolved - created).total_seconds() / 3600)

    avg_resolution_hours = round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else None

    return {
        "range_days": range_days,
        "kpis": {
            "total_tickets": len(in_range),
            "unread_messages": unread_total,
            "sla_breached": sla_breached,
            "avg_resolution_hours": avg_resolution_hours,
            "open_tickets": status_counts.get("open", 0) + status_counts.get("reopened", 0),
        },
        "breakdowns": {
            "status": status_counts,
            "priority": priority_counts,
            "category": category_counts,
        },
    }


@router.post("/ai/suggest-draft")
async def suggest_ticket_draft(payload: TicketAIDraftRequest, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from routes.db import EMERGENT_LLM_KEY

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI key unavailable")

    safe_tone = str(payload.tone or "professional").strip().lower()
    if safe_tone not in {"professional", "empathetic", "concise", "direct"}:
        safe_tone = "professional"

    safe_mode = str(payload.mode or "draft").strip().lower()
    if safe_mode not in {"draft", "rewrite"}:
        safe_mode = "draft"

    subject = (payload.subject or "").strip()[:200]
    message = (payload.message or "").strip()[:2000]
    category = (payload.category or "general").strip().lower()[:40]
    priority = (payload.priority or "medium").strip().lower()[:20]

    user_name = (getattr(user, "name", "") or "User").strip()[:80]

    system_message = (
        "You are an enterprise customer-support writing copilot. Return ONLY valid JSON. "
        "Never include markdown fences."
    )

    prompt = (
        "Generate JSON with keys: subject (string), message (string), rationale (string), tone (string).\n"
        f"mode={safe_mode}\n"
        f"tone={safe_tone}\n"
        f"category={category}\n"
        f"priority={priority}\n"
        f"user_name={user_name}\n"
        f"existing_subject={subject or '[empty]'}\n"
        f"existing_message={message or '[empty]'}\n"
        "Rules:\n"
        "- Subject max 120 chars, clear and specific.\n"
        "- Message 2-5 short paragraphs, actionable and polite.\n"
        "- If mode=rewrite, preserve issue facts and only improve clarity/tone.\n"
        "- If mode=draft and content is empty, infer a high-quality support request structure without inventing account facts.\n"
    )

    try:
        from utils.llm_helper import generate_verified_json

        response = await generate_verified_json(
            prompt=prompt,
            system_message=system_message,
            session_id=f"ticket-draft-{uuid.uuid4().hex[:8]}",
            model="gpt-4o",
            max_retries=2,
            feature="ticket_ai_draft",
            user_id=user.user_id,
        )

        suggested_subject = str(response.get("subject") or "").strip()[:200]
        suggested_message = str(response.get("message") or "").strip()[:2000]
        rationale = str(response.get("rationale") or "").strip()[:400]
        if not suggested_message:
            raise ValueError("AI returned empty message")
        if not suggested_subject:
            suggested_subject = subject or "Support request"

        log_doc = {
            "suggestion_id": f"ais_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "mode": safe_mode,
            "tone": safe_tone,
            "input": {
                "subject": subject,
                "message": message,
                "category": category,
                "priority": priority,
            },
            "output": {
                "subject": suggested_subject,
                "message": suggested_message,
                "rationale": rationale,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.ticket_ai_suggestions.insert_one(log_doc)

        return {
            "subject": suggested_subject,
            "message": suggested_message,
            "tone": safe_tone,
            "mode": safe_mode,
            "rationale": rationale,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ticket AI draft generation failed: {exc}")
        raise HTTPException(status_code=500, detail="AI draft generation failed")


def _generate_rating_token(ticket_id: str, rating: str) -> str:
    secret = str(os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET is missing or too short for secure rating token generation")
    return hmac.new(secret.encode(), f"{ticket_id}:{rating}".encode(), hashlib.sha256).hexdigest()[:16]


@router.get("/rate", response_class=HTMLResponse)
async def rate_ticket(ticket_id: str = "", rating: str = "", token: str = ""):
    """Public endpoint — user clicks thumbs up/down link in email."""
    if not ticket_id or rating not in ("positive", "negative") or not token:
        return HTMLResponse(
            _rating_page("Invalid Link", "This rating link is invalid or incomplete.", "#EF4444", ticket_id),
            status_code=400,
        )

    expected = _generate_rating_token(ticket_id, rating)
    if not hmac.compare_digest(token, expected):
        return HTMLResponse(
            _rating_page("Invalid Link", "This rating link is invalid or has expired.", "#EF4444", ticket_id),
            status_code=400,
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    updated = False
    for coll_name, id_field in [("support_tickets", "ticket_id"), ("support_submissions", "ticket_number")]:
        result = await db[coll_name].update_one(
            {id_field: ticket_id}, {"$set": {"csat_rating": rating, "csat_rated_at": now_iso}}
        )
        if result.matched_count > 0:
            updated = True
            break

    if not updated:
        return HTMLResponse(
            _rating_page("Ticket Not Found", f"We could not find ticket {ticket_id}.", "#F59E0B", ticket_id),
            status_code=404,
        )

    if rating == "positive":
        return HTMLResponse(
            _rating_page(
                "Thank You!",
                "We're glad we could help. Your positive feedback has been recorded.",
                "#10B981",
                ticket_id,
            )
        )
    return HTMLResponse(
        _rating_page(
            "Thank You for Your Feedback",
            "We're sorry the experience wasn't great. Your feedback has been recorded and will help us improve.",
            "#3B82F6",
            ticket_id,
        )
    )


def _rating_page(title: str, message: str, accent: str, ticket_id: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} - RealAICoach</title></head>
<body style="margin:0;padding:0;background:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:460px;margin:80px auto;padding:40px 32px;background:#fff;border-radius:20px;border:1px solid #E2E8F0;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.06);">
    <div style="width:56px;height:56px;border-radius:14px;background:{accent};margin:0 auto 20px;display:flex;align-items:center;justify-content:center;">
      <span style="color:#fff;font-size:26px;font-weight:800;line-height:56px;">R</span>
    </div>
    <h1 style="color:#0F172A;font-size:22px;font-weight:800;margin:0 0 10px;">{title}</h1>
    <p style="color:#64748B;font-size:14px;line-height:1.6;margin:0 0 20px;">{message}</p>
    <p style="color:#CBD5E1;font-size:11px;margin:0;">Ticket #{ticket_id} &middot; RealAICoach Support</p>
  </div>
</body></html>"""


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, request: Request):
    """Get a single ticket by submission_id or ticket_number."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ticket = await db.support_submissions.find_one(
        {"$or": [{"submission_id": ticket_id}, {"ticket_number": ticket_id}], "user_id": user.user_id}, {"_id": 0}
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return _normalize_ticket_for_user(ticket)


@router.post("/{ticket_id}/mark-read")
async def mark_ticket_read(ticket_id: str, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ticket = await db.support_submissions.find_one(
        {"$or": [{"submission_id": ticket_id}, {"ticket_number": ticket_id}], "user_id": user.user_id},
        {"_id": 0, "submission_id": 1},
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.support_submissions.update_one(
        {"submission_id": ticket["submission_id"]},
        {"$set": {"last_user_read_at": now_iso, "updated_at": now_iso}},
    )
    return {"success": True, "submission_id": ticket["submission_id"], "read_at": now_iso}


@router.post("/{ticket_id}/reply")
async def reply_to_ticket(ticket_id: str, payload: TicketReply, request: Request):
    """User replies to their own ticket."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ticket = await db.support_submissions.find_one(
        {"$or": [{"submission_id": ticket_id}, {"ticket_number": ticket_id}], "user_id": user.user_id},
        {"_id": 0, "submission_id": 1, "ticket_number": 1, "status": 1, "subject": 1},
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.get("status") in ("closed", "resolved"):
        raise HTTPException(
            status_code=400, detail="Cannot reply to a closed/resolved ticket. Please create a new ticket."
        )

    # Resolve reply attachments
    reply_attachments = []
    for att_id in payload.attachment_ids[:MAX_ATTACHMENTS]:
        att = await db.ticket_attachments.find_one({"file_id": att_id, "uploaded_by": user.user_id}, {"_id": 0})
        if att:
            reply_attachments.append(
                {
                    "file_id": att["file_id"],
                    "original_name": att["original_name"],
                    "size": att["size"],
                    "mime_type": att["mime_type"],
                }
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "$set": {"status": "open", "updated_at": now_iso, "last_user_read_at": now_iso},
        "$push": {
            "reply_logs": {
                "from": getattr(user, "email", ""),
                "from_name": getattr(user, "name", "User"),
                "message": payload.message,
                "role": "user",
                "at": now_iso,
                "attachments": reply_attachments,
            },
            "history": {
                "action": "user_reply",
                "note": payload.message[:100],
                "by": user.user_id,
                "by_name": getattr(user, "name", "User"),
                "at": now_iso,
            },
        },
    }

    await db.support_submissions.update_one({"submission_id": ticket["submission_id"]}, update)

    # Notify admins about user reply (in-app + email)
    try:
        from routes.notification_engine import emit_notification

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(10)
        ticket_num = ticket.get("ticket_number", ticket_id[:8])
        ticket_subject = ticket.get("subject", "Support Request")
        user_name = getattr(user, "name", "User")
        user_email = getattr(user, "email", "")

        for admin in admins:
            await emit_notification(
                user_id=admin["user_id"],
                notif_type="ticket_user_reply",
                title=f"User Reply: {ticket_num}",
                body=f"{user_name} replied: {payload.message[:80]}",
                action_url="/admin-console",
            )

        # Send email to admins about user reply
        try:
            from utils.email_service import is_resend_configured, is_email_configured
            from utils.email_service import render_email_logo

            if is_resend_configured() or is_email_configured():
                frontend_url = os.environ.get("FRONTEND_BASE_URL", "")
                logo_html = render_email_logo(variant="admin")
                for admin in admins:
                    admin_email = admin.get("email", "")
                    if not admin_email:
                        continue
                    f"""
                    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:520px;margin:0 auto;padding:32px 16px;background:#0B0F1A;">
                      <div style="border-radius:20px;overflow:hidden;border:1px solid #1E293B;">
                        <div style="background:linear-gradient(135deg,#0ea5e9,#6366f1);padding:36px 28px 28px;">
                          {logo_html}
                          <div style="color:rgba(255,255,255,0.7);font-size:12px;margin-bottom:14px;">RealAICoach &middot; Admin Alert</div>
                          <h2 style="color:#FFFFFF;font-size:20px;font-weight:800;margin:0 0 6px;">New User Reply</h2>
                          <p style="color:rgba(255,255,255,0.82);font-size:13px;margin:0;">Ticket #{ticket_num} — {ticket_subject}</p>
                        </div>
                        <div style="background:#111827;padding:24px 28px;">
                          <p style="color:#CBD5E1;font-size:13px;margin:0 0 12px;"><strong style="color:#F8FAFC;">{user_name}</strong> ({user_email}) replied:</p>
                          <div style="background:#0F172A;border-left:3px solid #F59E0B;border-radius:0 10px 10px 0;padding:16px;margin-bottom:20px;">
                            <div style="white-space:pre-line;color:#CBD5E1;font-size:14px;line-height:1.7;">{payload.message[:500]}</div>
                          </div>
                          <div style="text-align:center;">
                            <a href="{frontend_url}/admin-console" style="display:inline-block;padding:12px 32px;background:#F59E0B;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">View & Reply in Admin Console</a>
                          </div>
                        </div>
                      </div>
                      <p style="text-align:center;color:#475569;font-size:11px;margin-top:16px;">RealAICoach Admin Notification</p>
                    </div>"""
                    from utils.email_service import send_catalog_template
                    await send_catalog_template(
                        recipient_email=admin_email,
                        template_key="ticket_reply_agent",
                        recipient_name=admin.get("name", "Admin"),
                        user_name=admin.get("name", "Admin"),
                        ticket_id=ticket_num,
                        ticket_subject=ticket_subject,
                        agent_name=getattr(user, "name", "User"),
                        reply_preview=payload.message[:300],
                    )
        except Exception as e:
            logger.error(f"Admin email notification failed: {e}")
    except Exception as e:
        logger.error(f"Admin ticket reply notification failed: {e}")

    from utils.ws_manager import broadcast_data_change
    await broadcast_data_change("tickets", "updated", user.user_id)

    return {"success": True, "message": "Reply sent"}


@router.post("/{ticket_id}/reopen")
async def reopen_ticket(ticket_id: str, request: Request):
    """User reopens a resolved/closed ticket."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ticket = await db.support_submissions.find_one(
        {"$or": [{"submission_id": ticket_id}, {"ticket_number": ticket_id}], "user_id": user.user_id},
        {"_id": 0, "submission_id": 1, "status": 1},
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.get("status") not in ("resolved", "closed"):
        raise HTTPException(status_code=400, detail="Only resolved/closed tickets can be reopened")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.support_submissions.update_one(
        {"submission_id": ticket["submission_id"]},
        {
            "$set": {"status": "reopened", "updated_at": now_iso},
            "$push": {
                "history": {
                    "action": "reopened",
                    "note": "Ticket reopened by user",
                    "by": user.user_id,
                    "by_name": getattr(user, "name", "User"),
                    "at": now_iso,
                }
            },
        },
    )

    from utils.ws_manager import broadcast_data_change
    await broadcast_data_change("tickets", "updated", user.user_id)

    return {"success": True, "status": "reopened"}



@router.post("/{ticket_id}/satisfaction")
async def submit_satisfaction(ticket_id: str, request: Request):
    """User submits a 1-5 star satisfaction rating + optional comment for a resolved/closed ticket."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    rating = body.get("rating")
    comment = (body.get("comment") or "").strip()[:500]

    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    ticket = await db.support_submissions.find_one(
        {"$or": [{"submission_id": ticket_id}, {"ticket_number": ticket_id}], "user_id": user.user_id},
        {"_id": 0, "submission_id": 1, "status": 1, "satisfaction": 1},
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.get("satisfaction"):
        raise HTTPException(status_code=400, detail="Already rated")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.support_submissions.update_one(
        {"submission_id": ticket["submission_id"]},
        {
            "$set": {
                "satisfaction": {
                    "rating": rating,
                    "comment": comment,
                    "rated_at": now_iso,
                    "rated_by": user.user_id,
                },
                "updated_at": now_iso,
            },
            "$push": {
                "history": {
                    "action": "satisfaction_rated",
                    "note": f"Rated {rating}/5" + (f": {comment[:60]}" if comment else ""),
                    "by": user.user_id,
                    "by_name": getattr(user, "name", "User"),
                    "at": now_iso,
                }
            },
        },
    )

    from utils.ws_manager import broadcast_data_change
    await broadcast_data_change("tickets", "updated", user.user_id)

    return {"success": True, "rating": rating}
