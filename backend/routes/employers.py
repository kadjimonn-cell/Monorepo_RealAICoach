"""Employer Approval System — Application, Review, Post-Approval Unlock, Automated Workflows."""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
import uuid
import os
import logging
import json
import base64
import binascii
import re

from .db import db, get_current_user, User
from .employers_read_service import (
    admin_employer_communications_read,
    admin_get_application_read,
    check_reverify_status_read,
    download_employer_document_read,
    get_employer_messages_read,
    get_my_application_read,
    get_my_permissions_read,
)
from utils.email_service import render_email_logo
from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.object_storage_service import put_bytes
from utils.file_security_service import enforce_file_security

router = APIRouter(prefix="/employers")
logger = logging.getLogger("routes.employers")

RE_VERIFICATION_COOLDOWN_DAYS = 14
SUPPORT_REVIEW_MESSAGE = "In Review — Please allow 7 business days for our support team to review your application."
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")

HIGH_RISK_COUNTRIES = {
    "unknown",
    "n/a",
}

GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
}


# ── Models ──


class EmployerApplication(BaseModel):
    business_name: str
    registration_number: str
    country: str
    business_email: str
    industry: str
    website: Optional[str] = None
    contact_person_name: str
    contact_person_phone: str
    contact_person_role: Optional[str] = None
    description: Optional[str] = None
    documents: Optional[List["EmployerKycDocumentPayload"]] = None


class EmployerKycDocumentPayload(BaseModel):
    document_key: str
    filename: str
    content_type: str
    data_base64: str


class AdminReviewAction(BaseModel):
    action: str  # approve, reject, request_info, hold, escalate
    reason: Optional[str] = None
    internal_note: Optional[str] = None
    checklist_doc_completeness: Optional[bool] = None
    checklist_identity_match: Optional[bool] = None
    checklist_fraud_risk_reviewed: Optional[bool] = None


class AccessControlAction(BaseModel):
    action: str  # suspend, revoke, restore
    reason: Optional[str] = None
    internal_note: Optional[str] = None


# ── Helpers ──

VALID_STATUSES = ["pending", "in_review", "approved", "rejected", "on_hold", "needs_info", "escalated"]
EMPLOYER_PERMISSIONS = ["post_job", "manage_jobs", "view_applicants", "hire_candidate", "employer_analytics"]

ALLOWED_DOC_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}
MANDATORY_KYC_KEYS = {"business_registration", "id_front", "id_back"}
EMPLOYER_DOC_APP_PREFIX = "realaicoach-employer-docs"


def _safe_filename(filename: str, fallback: str = "document") -> str:
    base = str(filename or "").strip() or fallback
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return base[:120]


def _validate_content_type(content_type: str) -> str:
    normalized = str(content_type or "").strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized not in ALLOWED_DOC_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Allowed: PDF, JPG, PNG, WebP",
        )
    return normalized


def _decode_base64_bytes(data_base64: str) -> bytes:
    raw = str(data_base64 or "").strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 payload for document")


def _build_object_storage_path(*, employer_id: str, doc_id: str, filename: str) -> str:
    safe = _safe_filename(filename)
    return f"{EMPLOYER_DOC_APP_PREFIX}/{employer_id}/{doc_id}_{safe}"


def _assert_doc_size(content: bytes) -> None:
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum: 10MB")
    if len(content) < 1024:
        raise HTTPException(status_code=400, detail="File too small or empty")


def _legacy_local_doc_path(employer_id: str, filename: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "media",
        "employer_docs",
        employer_id,
        filename,
    )


async def require_auth(request: Request) -> User:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(request: Request) -> User:
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _log_audit(employer_id: str, action: str, actor_id: str, details: dict = None):
    await db.employer_audit_log.insert_one(
        {
            "audit_id": f"aud_{uuid.uuid4().hex[:12]}",
            "employer_id": employer_id,
            "action": action,
            "actor_id": actor_id,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _email_domain(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[1].strip().lower()


def _compute_risk_profile(app_doc: Dict) -> Dict:
    score = 8
    flags: List[str] = []

    if not app_doc.get("website"):
        score += 14
        flags.append("missing_website")

    domain = _email_domain(app_doc.get("business_email", ""))
    if domain in GENERIC_EMAIL_DOMAINS:
        score += 18
        flags.append("generic_email_domain")

    reg_num = str(app_doc.get("registration_number", "") or "").strip()
    if len(reg_num) < 6:
        score += 12
        flags.append("weak_registration_number")

    docs = app_doc.get("documents") or []
    if len(docs) == 0:
        score += 20
        flags.append("no_verification_documents")
    elif len(docs) < 2:
        score += 8
        flags.append("minimal_verification_documents")

    country = str(app_doc.get("country", "") or "").strip().lower()
    if country in HIGH_RISK_COUNTRIES:
        score += 15
        flags.append("country_unverified")

    industry = str(app_doc.get("industry", "") or "").strip().lower()
    if industry in {"crypto", "gambling", "forex", "adult"}:
        score += 10
        flags.append("high_risk_industry")

    score = max(0, min(100, score))
    if score >= 70:
        level = "high_risk"
    elif score >= 35:
        level = "suspicious"
    else:
        level = "safe"

    return {
        "risk_score": score,
        "risk_level": level,
        "trust_score": max(0, 100 - score),
        "fraud_flags": flags,
        "risk_updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _ensure_risk_profile(app_doc: Dict) -> Dict:
    """Backfill risk fields for legacy employer applications."""
    if not app_doc:
        return app_doc
    if app_doc.get("risk_score") is not None and app_doc.get("risk_level"):
        return app_doc

    profile = _compute_risk_profile(app_doc)
    employer_id = app_doc.get("employer_id")
    if employer_id:
        await db.employer_applications.update_one({"employer_id": employer_id}, {"$set": profile})
    return {**app_doc, **profile}


async def _ai_fraud_assessment(app_doc: Dict) -> Dict:
    if not EMERGENT_KEY:
        return {
            "summary": "AI risk assistant unavailable (missing key).",
            "signals": [],
            "confidence": "low",
        }

    profile = {
        "business_name": app_doc.get("business_name"),
        "registration_number": app_doc.get("registration_number"),
        "country": app_doc.get("country"),
        "industry": app_doc.get("industry"),
        "business_email": app_doc.get("business_email"),
        "website": app_doc.get("website"),
        "documents_count": len(app_doc.get("documents") or []),
        "fraud_flags": app_doc.get("fraud_flags") or [],
        "risk_score": app_doc.get("risk_score"),
        "risk_level": app_doc.get("risk_level"),
    }

    prompt = (
        "Act as enterprise fraud analyst. Review employer onboarding profile and return compact JSON with keys "
        "summary (string), signals (array of strings), recommended_action (approve/review/reject), confidence (low/medium/high). "
        f"Profile: {json.dumps(profile)}"
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"employer_risk_{app_doc.get('employer_id', uuid.uuid4().hex[:8])}",
            system_message="You output strict JSON only.",
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=prompt))
        parsed = json.loads(response)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.warning(f"AI fraud assessment failed: {e}")

    return {
        "summary": "AI assessment unavailable. Use manual review checklist.",
        "signals": [],
        "recommended_action": "review",
        "confidence": "low",
    }


async def _log_email_event(
    employer_id: str,
    recipient_email: str,
    subject: str,
    template_key: str,
    status: str,
    actor_id: str = "system",
    metadata: Optional[Dict] = None,
):
    await db.employer_email_logs.insert_one(
        {
            "email_log_id": f"elog_{uuid.uuid4().hex[:12]}",
            "employer_id": employer_id,
            "recipient_email": recipient_email,
            "subject": subject,
            "template_key": template_key,
            "status": status,
            "actor_id": actor_id,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def _send_notification(user_id: str, title: str, body: str, notif_type: str, action_url: str = None):
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user_id,
            notif_type=notif_type,
            title=title,
            body=body,
            action_url=action_url or "/job-platform",
        )
    except Exception as e:
        logger.error(f"Notification engine failed, fallback: {e}")
        await db.notifications.insert_one(
            {
                "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "type": notif_type,
                "title": title,
                "body": body,
                "message": body,
                "action_url": action_url or "/job-platform",
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )


async def _send_employer_email(
    email: str,
    name: str,
    subject: str,
    body_html: str,
    employer_id: Optional[str] = None,
    actor_id: str = "system",
):
    """Send email notification and persist communication timeline logs."""
    status = "skipped"
    provider_meta: Dict = {}
    try:
        from utils.email_service import send_catalog_template, is_email_configured

        if is_email_configured():
            result = await send_catalog_template(
                recipient_email=email,
                template_key="employer_notification_v7",
                recipient_name=name,
                event_type=subject[:50],
                summary=body_html[:200] if body_html else subject,
            )
            if result.get("success"):
                status = "sent"
                logger.info(f"Employer email sent to {email}: {subject}")
            else:
                status = "failed"
                provider_meta = {"error": result.get("error", "unknown")}
                logger.error(f"Employer email failed: {result.get('error')}")
        else:
            status = "disabled"
    except Exception as e:
        status = "failed"
        provider_meta = {"error": str(e)}
        logger.error(f"Employer email exception: {e}")

    if employer_id:
        try:
            await _log_email_event(
                employer_id=employer_id,
                recipient_email=email,
                subject=subject,
                template_key="employer_notification_v7",
                status=status,
                actor_id=actor_id,
                metadata=provider_meta,
            )
        except Exception as e:
            logger.warning(f"Failed to record email timeline event: {e}")

    return {"success": status == "sent", "status": status, "meta": provider_meta}


def _build_employer_status_email(name: str, status: str, reason: str = "") -> str:
    """Build HTML email for employer status changes."""
    status_colors = {
        "approved": "#10B981",
        "rejected": "#EF4444",
        "needs_info": "#F59E0B",
        "in_review": "#3B82F6",
        "on_hold": "#8B5CF6",
        "escalated": "#EC4899",
    }
    color = status_colors.get(status, "#6B7280")
    status_label = status.replace("_", " ").title()

    body_text = {
        "approved": "Your employer application has been approved! You now have full access to the Employer Dashboard, Job Posting, Candidate Hiring, Recruitment Tools, Analytics, and more.",
        "rejected": f"Your employer application has been rejected. {('Reason: ' + reason) if reason else ''} {SUPPORT_REVIEW_MESSAGE} After 14 business days, re-verification will be automatically unlocked.",
        "needs_info": f"Your employer application requires additional information. {('Details: ' + reason) if reason else 'Please check your dashboard for details.'}",
        "in_review": SUPPORT_REVIEW_MESSAGE,
        "on_hold": "Your employer application is currently on hold for further review.",
        "escalated": "Your application has been escalated for senior review.",
    }.get(status, f"Your application status has been updated to: {status_label}")

    logo_html = render_email_logo(variant="admin")
    return f"""
    <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;background:#0F1117;color:#E5E7EB;border-radius:16px;overflow:hidden;">
      <div style="background:{color};padding:28px;text-align:center;">
        {logo_html}
        <div style="font-size:22px;font-weight:800;color:#fff;">Employer Application Update</div>
        <div style="font-size:16px;color:rgba(255,255,255,0.9);margin-top:8px;text-transform:uppercase;letter-spacing:1px;">{status_label}</div>
      </div>
      <div style="padding:24px;">
        <p style="color:#D1D5DB;font-size:14px;line-height:1.6;margin:0 0 12px;">Hi {name},</p>
        <p style="color:#D1D5DB;font-size:14px;line-height:1.6;margin:0 0 16px;">{body_text}</p>
        <p style="color:#6B7280;font-size:12px;text-align:center;margin-top:24px;">RealAICoach Employer Platform</p>
      </div>
    </div>"""


async def _auto_validate_application(employer_id: str) -> Optional[str]:
    """Auto-validate employer application. Returns suggested status or None."""
    app_doc = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    if not app_doc:
        return None

    required_fields = [
        "business_name",
        "registration_number",
        "country",
        "business_email",
        "industry",
        "contact_person_name",
        "contact_person_phone",
    ]
    missing = [f for f in required_fields if not app_doc.get(f)]
    if missing:
        return "needs_info"

    has_docs = len(app_doc.get("documents", [])) > 0
    if not has_docs:
        return None  # Wait for documents

    return "pending"


async def _process_kyc_documents_from_payload(
    *,
    employer_id: str,
    docs_payload: List[EmployerKycDocumentPayload],
) -> List[Dict[str, Any]]:
    processed_docs: List[Dict[str, Any]] = []

    for item in docs_payload:
        document_key = str(item.document_key or "").strip().lower()
        if not document_key:
            raise HTTPException(status_code=400, detail="Each document must include document_key")

        content_type = _validate_content_type(item.content_type)
        content = _decode_base64_bytes(item.data_base64)
        _assert_doc_size(content)
        try:
            security = enforce_file_security(
                content=content,
                claimed_content_type=content_type,
                allowed_content_types=ALLOWED_DOC_CONTENT_TYPES,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"File security validation failed: {str(e)}")

        sniffed_content_type = str(security.get("sniffed_content_type") or content_type)

        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        storage_path = _build_object_storage_path(
            employer_id=employer_id,
            doc_id=doc_id,
            filename=item.filename,
        )

        put_result = put_bytes(storage_path, content, sniffed_content_type)
        if not put_result:
            raise HTTPException(status_code=503, detail="Document storage unavailable. Please retry.")

        processed_docs.append(
            {
                "doc_id": doc_id,
                "type": document_key,
                "purpose": "business_verification" if document_key == "business_registration" else "id_verification",
                "filename": _safe_filename(item.filename, fallback=f"{document_key}.bin"),
                "original_filename": str(item.filename or "").strip() or _safe_filename(item.filename),
                "file_size": len(content),
                "content_type": sniffed_content_type,
                "checksum_sha256": security.get("checksum_sha256"),
                "security_scan": security.get("antivirus"),
                "storage_path": str(put_result.get("path") or storage_path),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    uploaded_keys = {str(doc.get("type") or "") for doc in processed_docs}
    missing = sorted(MANDATORY_KYC_KEYS - uploaded_keys)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing required employer verification documents",
                "missing_document_keys": missing,
            },
        )

    return processed_docs


# ── Employer Application Endpoints ──


@router.post("/apply")
async def submit_employer_application(application: EmployerApplication, request: Request):
    """Submit an employer application. Any authenticated user can apply."""
    user = await require_auth(request)

    existing = await db.employer_applications.find_one(
        {"user_id": user.user_id, "status": {"$nin": ["rejected"]}}, {"_id": 0}
    )
    if existing:
        if existing.get("status") == "approved":
            raise HTTPException(status_code=400, detail="You are already an approved employer")
        raise HTTPException(
            status_code=400, detail=f"You have a pending application (status: {existing.get('status')})"
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    employer_id = f"emp_{uuid.uuid4().hex[:12]}"

    docs_payload = application.documents or []
    if not docs_payload:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Required verification documents are missing",
                "missing_document_keys": sorted(MANDATORY_KYC_KEYS),
            },
        )

    processed_docs = await _process_kyc_documents_from_payload(
        employer_id=employer_id,
        docs_payload=docs_payload,
    )

    app_doc = {
        "employer_id": employer_id,
        "user_id": user.user_id,
        "email": getattr(user, "email", ""),
        "status": "pending",
        "business_name": application.business_name,
        "registration_number": application.registration_number,
        "country": application.country,
        "business_email": application.business_email,
        "industry": application.industry,
        "website": application.website,
        "contact_person_name": application.contact_person_name,
        "contact_person_phone": application.contact_person_phone,
        "contact_person_role": application.contact_person_role,
        "description": application.description,
        "documents": processed_docs,
        "internal_notes": [],
        "fraud_flags": [],
        "permissions": [],
        "submitted_at": now_iso,
        "updated_at": now_iso,
        "ip_address": request.client.host if request.client else "unknown",
    }

    risk_profile = _compute_risk_profile(app_doc)
    app_doc.update(risk_profile)
    app_doc["ai_risk_assessment"] = None

    await db.employer_applications.insert_one(app_doc)
    await _log_audit(employer_id, "application_submitted", user.user_id, {"business_name": application.business_name})
    await _send_notification(
        user.user_id,
        "Application Submitted",
        "Your employer application has been submitted and is pending review.",
        "employer_status",
    )

    # Send confirmation email
    email = getattr(user, "email", "") or application.business_email
    name = getattr(user, "name", application.contact_person_name)
    await _send_employer_email(
        email,
        name,
        "Employer Application Received",
        _build_employer_status_email(name, "in_review"),
        employer_id=employer_id,
        actor_id=user.user_id,
    )

    # Notify all admins about new application
    try:
        from routes.notification_engine import emit_notification

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(10)
        for admin in admins:
            await emit_notification(
                user_id=admin["user_id"],
                notif_type="new_employer_application",
                title=f"New Employer Application: {application.business_name}",
                body=f"{application.contact_person_name} ({application.business_email}) from {application.country}",
                action_url="/admin-console",
            )
    except Exception as e:
        logger.error(f"Admin employer notification failed: {e}")

    # Run auto-validation
    auto_status = await _auto_validate_application(employer_id)
    if auto_status and auto_status != "pending":
        await db.employer_applications.update_one(
            {"employer_id": employer_id},
            {"$set": {"status": auto_status, "auto_validated": True, "updated_at": now_iso}},
        )
        app_doc["status"] = auto_status
        await _log_audit(employer_id, f"auto_validated_{auto_status}", "system")

    app_doc.pop("_id", None)
    return {
        "success": True,
        "employer_id": employer_id,
        "status": app_doc.get("status", "pending"),
        "application": app_doc,
    }


@router.post("/upload-document")
async def upload_employer_document(
    request: Request,
    document_type: str = Form(...),
    document_role: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    """Upload a verification document for the employer application."""
    user = await require_auth(request)

    application = await db.employer_applications.find_one(
        {"user_id": user.user_id, "status": {"$nin": ["approved"]}}, {"_id": 0}
    )
    if not application:
        raise HTTPException(status_code=404, detail="No active application found")

    content_type = _validate_content_type(file.content_type)

    content = await file.read()
    _assert_doc_size(content)
    try:
        security = enforce_file_security(
            content=content,
            claimed_content_type=content_type,
            allowed_content_types=ALLOWED_DOC_CONTENT_TYPES,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"File security validation failed: {str(e)}")

    sniffed_content_type = str(security.get("sniffed_content_type") or content_type)

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "pdf"
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    filename = f"{doc_id}_{_safe_filename(document_type)}.{ext}"
    storage_path = _build_object_storage_path(
        employer_id=application["employer_id"],
        doc_id=doc_id,
        filename=filename,
    )
    put_result = put_bytes(storage_path, content, sniffed_content_type)
    if not put_result:
        raise HTTPException(status_code=503, detail="Document storage unavailable. Please retry.")

    doc_entry = {
        "doc_id": doc_id,
        "type": document_type,
        "role": document_role,
        "purpose": "id_verification" if str(document_type).startswith("id_") else "business_verification",
        "filename": filename,
        "original_filename": file.filename or filename,
        "file_size": len(content),
        "content_type": sniffed_content_type,
        "checksum_sha256": security.get("checksum_sha256"),
        "security_scan": security.get("antivirus"),
        "storage_path": str(put_result.get("path") or storage_path),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.employer_applications.update_one(
        {"employer_id": application["employer_id"]},
        {"$push": {"documents": doc_entry}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )

    refreshed = await db.employer_applications.find_one({"employer_id": application["employer_id"]}, {"_id": 0})
    if refreshed:
        risk_profile = _compute_risk_profile(refreshed)
        await db.employer_applications.update_one({"employer_id": application["employer_id"]}, {"$set": risk_profile})

    return {"success": True, "document": doc_entry}


async def get_my_application(request: Request):
    user = await require_auth(request)
    return await get_my_application_read(user_id=user.user_id)


async def download_employer_document(employer_id: str, doc_id: str, request: Request):
    user = await require_auth(request)
    return await download_employer_document_read(
        employer_id=employer_id,
        doc_id=doc_id,
        user_id=user.user_id,
        is_admin=bool(getattr(user, "is_admin", False) or getattr(user, "role", "") == "admin"),
    )


async def get_my_permissions(request: Request):
    user = await require_auth(request)
    return await get_my_permissions_read(user_id=user.user_id)


@router.post("/resubmit-info")
async def resubmit_employer_info(payload: EmployerApplication, request: Request):
    """Resubmit information after admin requests more info."""
    user = await require_auth(request)

    application = await db.employer_applications.find_one({"user_id": user.user_id, "status": "needs_info"}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=400, detail="No application requiring additional info found")

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "business_name": payload.business_name,
        "registration_number": payload.registration_number,
        "country": payload.country,
        "business_email": payload.business_email,
        "industry": payload.industry,
        "website": payload.website,
        "contact_person_name": payload.contact_person_name,
        "contact_person_phone": payload.contact_person_phone,
        "contact_person_role": payload.contact_person_role,
        "description": payload.description,
        "status": "in_review",
        "updated_at": now_iso,
    }

    await db.employer_applications.update_one({"employer_id": application["employer_id"]}, {"$set": update})
    refreshed = await db.employer_applications.find_one({"employer_id": application["employer_id"]}, {"_id": 0})
    if refreshed:
        risk_profile = _compute_risk_profile(refreshed)
        await db.employer_applications.update_one({"employer_id": application["employer_id"]}, {"$set": risk_profile})
    await _log_audit(application["employer_id"], "info_resubmitted", user.user_id)
    await _send_notification(
        user.user_id,
        "Application Updated",
        "Your updated information has been resubmitted for review.",
        "employer_status",
    )

    return {"success": True, "status": "in_review"}


# ── Admin Endpoints ──


async def admin_employer_stats(request: Request):
    """Admin: Get employer application statistics."""
    await require_admin(request)

    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    result = await db.employer_applications.aggregate(pipeline).to_list(20)
    stats = {r["_id"]: r["count"] for r in result}
    total = sum(stats.values())

    # Industry breakdown
    industry_pipeline = [
        {"$group": {"_id": "$industry", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    industry_result = await db.employer_applications.aggregate(industry_pipeline).to_list(10)

    # Country breakdown
    country_pipeline = [{"$group": {"_id": "$country", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 20}]
    country_result = await db.employer_applications.aggregate(country_pipeline).to_list(20)

    risk_pipeline = [{"$group": {"_id": "$risk_level", "count": {"$sum": 1}}}]
    risk_result = await db.employer_applications.aggregate(risk_pipeline).to_list(10)
    risk_distribution = {r.get("_id") or "unknown": r.get("count", 0) for r in risk_result}

    avg_trust_pipeline = [{"$match": {"trust_score": {"$type": "number"}}}, {"$group": {"_id": None, "avg": {"$avg": "$trust_score"}}}]
    trust_avg = await db.employer_applications.aggregate(avg_trust_pipeline).to_list(1)
    avg_trust_score = round(float(trust_avg[0].get("avg", 0)), 1) if trust_avg else 0

    # Average approval time
    approved_pipeline = [
        {"$match": {"status": "approved", "approved_at": {"$exists": True}}},
        {
            "$project": {
                "approval_time": {
                    "$subtract": [
                        {"$dateFromString": {"dateString": "$approved_at"}},
                        {"$dateFromString": {"dateString": "$submitted_at"}},
                    ]
                }
            }
        },
        {"$group": {"_id": None, "avg_time_ms": {"$avg": "$approval_time"}}},
    ]
    try:
        avg_result = await db.employer_applications.aggregate(approved_pipeline).to_list(1)
        avg_approval_hours = round((avg_result[0]["avg_time_ms"] / 3600000), 1) if avg_result else None
    except Exception:
        avg_approval_hours = None

    return {
        "total": total,
        "pending": stats.get("pending", 0),
        "in_review": stats.get("in_review", 0),
        "approved": stats.get("approved", 0),
        "rejected": stats.get("rejected", 0),
        "on_hold": stats.get("on_hold", 0),
        "needs_info": stats.get("needs_info", 0),
        "escalated": stats.get("escalated", 0),
        "approval_rate": round((stats.get("approved", 0) / total * 100), 1) if total > 0 else 0,
        "avg_approval_hours": avg_approval_hours,
        "industry_breakdown": [{"industry": r["_id"], "count": r["count"]} for r in industry_result],
        "country_breakdown": [{"country": r["_id"], "count": r["count"]} for r in country_result],
        "risk_distribution": risk_distribution,
        "avg_trust_score": avg_trust_score,
    }


async def admin_list_applications(
    request: Request,
    status: str = "all",
    risk_level: str = "all",
    page: int = 1,
    limit: int = 20,
):
    """Admin: List employer applications with filtering."""
    await require_admin(request)

    query = {}
    if status != "all" and status in VALID_STATUSES:
        query["status"] = status
    if risk_level != "all" and risk_level in {"safe", "suspicious", "high_risk"}:
        query["risk_level"] = risk_level

    total = await db.employer_applications.count_documents(query)
    skip = (page - 1) * limit

    cursor = db.employer_applications.find(query, {"_id": 0})
    if status in {"pending", "in_review", "all"}:
        cursor = cursor.sort([("risk_score", -1), ("submitted_at", -1)])
    else:
        cursor = cursor.sort("submitted_at", -1)

    applications = await cursor.skip(skip).limit(limit).to_list(limit)
    normalized_apps: List[Dict] = []
    for app_doc in applications:
        normalized_apps.append(await _ensure_risk_profile(app_doc))

    return {
        "applications": normalized_apps,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


async def admin_get_application(employer_id: str, request: Request):
    await require_admin(request)
    return await admin_get_application_read(employer_id=employer_id)


@router.post("/admin/review/{employer_id}")
async def admin_review_application(employer_id: str, payload: AdminReviewAction, request: Request):
    """Admin: Take action on an employer application."""
    admin = await require_admin(request)

    application = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    action = payload.action
    valid_actions = ["approve", "reject", "request_info", "hold", "escalate"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}")

    if action == "approve":
        checks = {
            "doc_completeness": bool(payload.checklist_doc_completeness),
            "identity_match": bool(payload.checklist_identity_match),
            "fraud_risk_reviewed": bool(payload.checklist_fraud_risk_reviewed),
        }
        if not all(checks.values()):
            raise HTTPException(status_code=400, detail="Approve checklist incomplete")
        if not str(payload.reason or "").strip():
            raise HTTPException(status_code=400, detail="Reviewer note is required when approving")

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now_iso, "reviewed_by": admin.user_id, "reviewed_at": now_iso}
    notif_title = ""
    notif_body = ""

    if action == "approve":
        update["status"] = "approved"
        update["approved_at"] = now_iso
        update["permissions"] = EMPLOYER_PERMISSIONS
        update["approval_checklist"] = {
            "doc_completeness": True,
            "identity_match": True,
            "fraud_risk_reviewed": True,
            "review_note": str(payload.reason or "").strip(),
            "reviewed_by": admin.user_id,
            "reviewed_at": now_iso,
        }
        notif_title = "Application Approved!"
        notif_body = "Your employer application has been approved. You can now post jobs and access hiring tools."
        # Update user role
        await db.users.update_one(
            {"user_id": application["user_id"]},
            {"$set": {"is_employer": True, "employer_id": employer_id}, "$addToSet": {"roles": "employer"}},
        )
    elif action == "reject":
        update["status"] = "rejected"
        update["rejection_reason"] = payload.reason or "Application did not meet requirements"
        update["reverify_unlock_at"] = (
            datetime.now(timezone.utc) + timedelta(days=RE_VERIFICATION_COOLDOWN_DAYS)
        ).isoformat()
        notif_title = "Application Update"
        notif_body = f"{SUPPORT_REVIEW_MESSAGE}"
    elif action == "request_info":
        update["status"] = "needs_info"
        update["info_requested"] = payload.reason or "Additional information needed"
        notif_title = "More Information Required"
        notif_body = f"Your employer application requires additional information: {payload.reason or 'Please check your dashboard'}."
    elif action == "hold":
        update["status"] = "on_hold"
        notif_title = "Application On Hold"
        notif_body = "Your employer application has been placed on hold for further review."
    elif action == "escalate":
        update["status"] = "escalated"
        notif_title = "Application Under Senior Review"
        notif_body = "Your application has been escalated for senior review."

    if payload.internal_note:
        await db.employer_applications.update_one(
            {"employer_id": employer_id},
            {
                "$push": {
                    "internal_notes": {"note": payload.internal_note, "author_id": admin.user_id, "created_at": now_iso}
                }
            },
        )

    await db.employer_applications.update_one({"employer_id": employer_id}, {"$set": update})
    await _log_audit(
        employer_id,
        f"admin_{action}",
        admin.user_id,
        {"reason": payload.reason, "internal_note": payload.internal_note},
    )
    await _send_notification(application["user_id"], notif_title, notif_body, f"employer_{action}")

    # Send email notification for the status change
    user_doc = await db.users.find_one({"user_id": application["user_id"]}, {"_id": 0, "email": 1, "name": 1})
    if user_doc:
        await _send_employer_email(
            user_doc.get("email", application.get("business_email", "")),
            user_doc.get("name", application.get("contact_person_name", "")),
            f"Employer Application: {action.replace('_', ' ').title()}",
            _build_employer_status_email(
                user_doc.get("name", ""),
                update.get("status", action),
                payload.reason or "",
            ),
            employer_id=employer_id,
            actor_id=admin.user_id,
        )

    updated = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    return {"success": True, "action": action, "application": updated}


@router.post("/admin/access-control/{employer_id}")
async def admin_access_control(employer_id: str, payload: AccessControlAction, request: Request):
    """Admin command center: instant suspend/revoke/restore employer access."""
    admin = await require_admin(request)

    application = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    action = payload.action
    if action not in {"suspend", "revoke", "restore"}:
        raise HTTPException(status_code=400, detail="Invalid action. Use suspend|revoke|restore")

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now_iso, "access_controlled_by": admin.user_id, "access_controlled_at": now_iso}

    if action == "suspend":
        update.update({"status": "on_hold", "access_state": "suspended", "permissions": []})
        await db.users.update_one(
            {"user_id": application["user_id"]},
            {"$set": {"is_employer": False}, "$pull": {"roles": "employer"}},
        )
        notif_title = "Employer Access Suspended"
        notif_body = f"Your employer access has been suspended. {payload.reason or ''}".strip()
    elif action == "revoke":
        update.update({"status": "rejected", "access_state": "revoked", "permissions": []})
        await db.users.update_one(
            {"user_id": application["user_id"]},
            {"$set": {"is_employer": False}, "$pull": {"roles": "employer"}},
        )
        notif_title = "Employer Access Revoked"
        notif_body = f"Your employer access has been revoked. {payload.reason or ''}".strip()
    else:
        update.update({"status": "approved", "access_state": "active", "permissions": EMPLOYER_PERMISSIONS})
        await db.users.update_one(
            {"user_id": application["user_id"]},
            {"$set": {"is_employer": True, "employer_id": employer_id}, "$addToSet": {"roles": "employer"}},
        )
        notif_title = "Employer Access Restored"
        notif_body = "Your employer access has been restored."

    await db.employer_applications.update_one({"employer_id": employer_id}, {"$set": update})

    if payload.internal_note:
        await db.employer_applications.update_one(
            {"employer_id": employer_id},
            {
                "$push": {
                    "internal_notes": {
                        "note": payload.internal_note,
                        "author_id": admin.user_id,
                        "created_at": now_iso,
                    }
                }
            },
        )

    await _log_audit(
        employer_id,
        f"admin_access_{action}",
        admin.user_id,
        {"reason": payload.reason, "internal_note": payload.internal_note},
    )
    await _send_notification(application["user_id"], notif_title, notif_body, "employer_access_control")

    user_doc = await db.users.find_one({"user_id": application["user_id"]}, {"_id": 0, "email": 1, "name": 1})
    if user_doc:
        await _send_employer_email(
            user_doc.get("email", application.get("business_email", "")),
            user_doc.get("name", application.get("contact_person_name", "")),
            notif_title,
            _build_employer_status_email(user_doc.get("name", ""), update.get("status", "on_hold"), payload.reason or ""),
            employer_id=employer_id,
            actor_id=admin.user_id,
        )

    refreshed = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    return {"success": True, "action": action, "application": refreshed}


async def admin_command_center(request: Request, status: str = "all", limit: int = 30):
    """High-priority verification queue with fraud/risk metrics for command center UX."""
    await require_admin(request)

    queue_query = {}
    if status != "all" and status in VALID_STATUSES:
        queue_query["status"] = status

    queue_docs = (
        await db.employer_applications.find(queue_query, {"_id": 0})
        .sort([("risk_score", -1), ("submitted_at", -1)])
        .limit(limit)
        .to_list(limit)
    )

    risk_counts_pipeline = [{"$group": {"_id": "$risk_level", "count": {"$sum": 1}}}]
    risk_counts_raw = await db.employer_applications.aggregate(risk_counts_pipeline).to_list(10)
    risk_counts = {r.get("_id") or "unknown": r.get("count", 0) for r in risk_counts_raw}

    pending_count = await db.employer_applications.count_documents({"status": {"$in": ["pending", "in_review"]}})
    high_risk_pending = await db.employer_applications.count_documents(
        {"status": {"$in": ["pending", "in_review"]}, "risk_level": "high_risk"}
    )

    queue = [
        {
            "employer_id": item.get("employer_id"),
            "business_name": item.get("business_name"),
            "country": item.get("country"),
            "industry": item.get("industry"),
            "status": item.get("status"),
            "risk_score": item.get("risk_score", 0),
            "risk_level": item.get("risk_level", "safe"),
            "trust_score": item.get("trust_score", 100),
            "fraud_flags": item.get("fraud_flags", []),
            "submitted_at": item.get("submitted_at"),
        }
        for item in [await _ensure_risk_profile(doc) for doc in queue_docs]
    ]

    return {
        "queue": queue,
        "metrics": {
            "pending_reviews": pending_count,
            "high_risk_pending": high_risk_pending,
            "risk_distribution": risk_counts,
        },
    }


@router.post("/admin/risk-assess/{employer_id}")
async def admin_run_ai_risk_assessment(employer_id: str, request: Request):
    """Manual + AI assisted fraud scoring refresh for admin review workflow."""
    admin = await require_admin(request)

    application = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    risk_profile = _compute_risk_profile(application)
    ai_assessment = await _ai_fraud_assessment({**application, **risk_profile})

    await db.employer_applications.update_one(
        {"employer_id": employer_id},
        {
            "$set": {
                **risk_profile,
                "ai_risk_assessment": ai_assessment,
                "ai_risk_assessed_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    await _log_audit(employer_id, "admin_ai_risk_assessment", admin.user_id, {"summary": ai_assessment.get("summary")})

    updated = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    return {
        "success": True,
        "employer_id": employer_id,
        "risk_profile": {
            "risk_score": updated.get("risk_score", 0),
            "risk_level": updated.get("risk_level", "safe"),
            "trust_score": updated.get("trust_score", 100),
            "fraud_flags": updated.get("fraud_flags", []),
        },
        "ai_assessment": updated.get("ai_risk_assessment") or {},
    }


async def admin_employer_communications(employer_id: str, request: Request):
    await require_admin(request)
    return await admin_employer_communications_read(employer_id=employer_id)


@router.post("/admin/add-note/{employer_id}")
async def admin_add_note(employer_id: str, request: Request):
    """Admin: Add an internal note to an application."""
    admin = await require_admin(request)
    body = await request.json()
    note_text = body.get("note", "")
    if not note_text:
        raise HTTPException(status_code=400, detail="Note text required")

    application = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0, "employer_id": 1})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.employer_applications.update_one(
        {"employer_id": employer_id},
        {"$push": {"internal_notes": {"note": note_text, "author_id": admin.user_id, "created_at": now_iso}}},
    )
    await _log_audit(employer_id, "note_added", admin.user_id, {"note": note_text[:100]})

    return {"success": True}


# ── Permission Middleware Helper ──


async def require_employer_permission(request: Request, permission: str) -> User:
    """Check that the user is an approved employer with the required permission."""
    user = await require_auth(request)
    application = await db.employer_applications.find_one(
        {"user_id": user.user_id, "status": "approved"}, {"_id": 0, "permissions": 1}
    )
    if not application:
        raise HTTPException(status_code=403, detail="You must be an approved employer to access this feature")
    permissions = application.get("permissions", [])
    if permission not in permissions:
        raise HTTPException(status_code=403, detail=f"Missing employer permission: {permission}")
    return user


# ── Communication Thread ──


class ThreadMessage(BaseModel):
    message: str


async def get_employer_messages(employer_id: str, request: Request):
    user = await require_auth(request)
    return await get_employer_messages_read(
        employer_id=employer_id,
        user_id=user.user_id,
        is_admin=bool(getattr(user, "is_admin", False) or getattr(user, "role", "") == "admin"),
    )


@router.post("/messages/{employer_id}")
async def post_employer_message(employer_id: str, payload: ThreadMessage, request: Request):
    """Post a message in the employer communication thread."""
    user = await require_auth(request)
    app_doc = await db.employer_applications.find_one(
        {"employer_id": employer_id}, {"_id": 0, "user_id": 1, "business_name": 1}
    )
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if app_doc["user_id"] != user.user_id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Access denied")

    is_admin = getattr(user, "is_admin", False)
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "employer_id": employer_id,
        "sender_id": user.user_id,
        "sender_name": getattr(user, "name", "Unknown"),
        "sender_role": "admin" if is_admin else "employer",
        "message": payload.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.employer_messages.insert_one(msg)
    msg.pop("_id", None)

    # Notify the other party
    if is_admin:
        await _send_notification(
            app_doc["user_id"],
            "New Message from Admin",
            f"Admin sent you a message regarding your employer application: {payload.message[:80]}",
            "employer_message",
            "/job-platform",
        )

        user_doc = await db.users.find_one({"user_id": app_doc["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        if user_doc and user_doc.get("email"):
            await _send_employer_email(
                user_doc.get("email"),
                user_doc.get("name", app_doc.get("business_name", "Employer")),
                "New message from Admin (Jobs Portal)",
                f"You have a new admin message: {payload.message[:160]}",
                employer_id=employer_id,
                actor_id=user.user_id,
            )
    else:
        # Notify all admins
        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(10)
        for admin in admins:
            await _send_notification(
                admin["user_id"],
                f"Employer Message: {app_doc.get('business_name', 'Employer')}",
                f"New message from employer: {payload.message[:80]}",
                "employer_message",
                "/admin-console",
            )
            if admin.get("email"):
                await _send_employer_email(
                    admin.get("email"),
                    admin.get("name", "Admin"),
                    f"Employer Message: {app_doc.get('business_name', 'Employer')}",
                    f"New employer message: {payload.message[:160]}",
                    employer_id=employer_id,
                    actor_id=user.user_id,
                )

    return {"success": True, "message": msg}


# ── Re-Verification Auto-Unlock ──


async def check_reverify_status(request: Request):
    user = await require_auth(request)
    return await check_reverify_status_read(user_id=user.user_id)


@router.post("/reverify")
async def start_reverification(request: Request):
    """Re-apply after rejection cooldown period has passed."""
    user = await require_auth(request)

    application = await db.employer_applications.find_one({"user_id": user.user_id, "status": "rejected"}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=400, detail="No rejected application found")

    unlock_at = application.get("reverify_unlock_at")
    if unlock_at:
        now = datetime.now(timezone.utc)
        unlock_dt = (
            datetime.fromisoformat(unlock_at.replace("Z", "+00:00")) if isinstance(unlock_at, str) else unlock_at
        )
        if now < unlock_dt:
            remaining = (unlock_dt - now).days
            raise HTTPException(
                status_code=400, detail=f"Re-verification not yet available. {remaining} days remaining."
            )

    # Reset the application to allow re-submission
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.employer_applications.update_one(
        {"employer_id": application["employer_id"]},
        {
            "$set": {
                "status": "pending",
                "reverify_unlock_at": None,
                "rejection_reason": None,
                "updated_at": now_iso,
            },
            "$push": {
                "history": {
                    "action": "re_verification_started",
                    "note": "User started re-verification after cooldown",
                    "at": now_iso,
                }
            },
        },
    )
    await _log_audit(application["employer_id"], "reverification_started", user.user_id)
    await _send_notification(
        user.user_id,
        "Re-Verification Started",
        "Your employer application is now under re-verification.",
        "employer_status",
    )

    return {
        "success": True,
        "status": "pending",
        "message": "Re-verification started. Your application is under review.",
    }


# ── Scheduled Job: Auto-unlock re-verification ──


async def auto_unlock_employer_reverification():
    """Background job: Automatically unlock re-verification for rejected employers after 14 days."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    expired = await db.employer_applications.find(
        {
            "status": "rejected",
            "reverify_unlock_at": {"$lte": now_iso, "$ne": None},
            "reverify_notified": {"$ne": True},
        },
        {"_id": 0, "employer_id": 1, "user_id": 1},
    ).to_list(50)

    for app_doc in expired:
        try:
            await db.employer_applications.update_one(
                {"employer_id": app_doc["employer_id"]}, {"$set": {"reverify_notified": True, "updated_at": now_iso}}
            )
            from routes.notification_engine import emit_notification

            await emit_notification(
                user_id=app_doc["user_id"],
                notif_type="employer_reverify_available",
                title="Re-Verification Available",
                body="Your employer application cooldown has expired. You can now re-apply for employer verification.",
                action_url="/job-platform",
            )
            logger.info(f"Auto-unlock re-verification for employer {app_doc['employer_id']}")
        except Exception as e:
            logger.error(f"Auto-unlock failed for {app_doc.get('employer_id')}: {e}")

    return len(expired)
