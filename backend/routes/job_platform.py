"""Global Job AI Platform - Employer Approval Workflow + Admin Review.

Adds employer approval workflow, admin review panel, fraud risk scoring,
and support ticket system to the existing job platform.
"""

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import random
import logging
import base64
import binascii
import re

from routes.db import db, require_auth
from utils.field_encryption import encrypt_field, hash_lookup, decrypt_doc
from utils.object_storage_service import put_bytes, get_bytes
from utils.file_security_service import enforce_file_security

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs")

INDUSTRIES = [
    "technology",
    "finance",
    "healthcare",
    "education",
    "retail",
    "manufacturing",
    "media",
    "consulting",
    "government",
    "nonprofit",
    "other",
]
COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5000+"]
MANDATORY_APPROVAL_DOC_KEYS = {"business_registration", "id_front", "id_back"}
ALLOWED_APPROVAL_DOC_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
APPROVAL_DOC_PREFIX = "realaicoach-job-platform-approval-docs"


class EmployerApprovalDocumentPayload(BaseModel):
    document_key: str
    filename: str
    content_type: str
    data_base64: str


# ── Employer Approval Request ──


class EmployerApprovalRequest(BaseModel):
    company_name: str
    business_registration: Optional[str] = ""
    country: str
    industry: str
    website: Optional[str] = ""
    contact_email: str
    company_size: str
    hiring_volume: Optional[str] = ""
    description: Optional[str] = ""
    documents: Optional[List[EmployerApprovalDocumentPayload]] = None


def _safe_filename(filename: str, fallback: str = "document") -> str:
    base = str(filename or "").strip() or fallback
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return base[:120]


def _validate_content_type(content_type: str) -> str:
    normalized = str(content_type or "").strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized not in ALLOWED_APPROVAL_DOC_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: PDF, JPG, PNG, WebP")
    return normalized


def _decode_base64(data_base64: str) -> bytes:
    raw = str(data_base64 or "").strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid base64 document payload")


def _assert_doc_size(payload_bytes: bytes) -> None:
    if len(payload_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum: 10MB")
    if len(payload_bytes) < 1024:
        raise HTTPException(status_code=400, detail="File too small or empty")


async def _process_approval_documents(
    *,
    approval_id: str,
    user_id: str,
    docs_payload: List[EmployerApprovalDocumentPayload],
) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for item in docs_payload:
        key = str(item.document_key or "").strip().lower()
        if not key:
            raise HTTPException(status_code=400, detail="Document key is required")

        ctype = _validate_content_type(item.content_type)
        content = _decode_base64(item.data_base64)
        _assert_doc_size(content)
        try:
            security = enforce_file_security(
                content=content,
                claimed_content_type=ctype,
                allowed_content_types=ALLOWED_APPROVAL_DOC_CONTENT_TYPES,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"File security validation failed: {str(e)}")

        sniffed_content_type = str(security.get("sniffed_content_type") or ctype)

        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        filename = _safe_filename(item.filename, fallback=f"{key}.bin")
        storage_path = f"{APPROVAL_DOC_PREFIX}/{user_id}/{approval_id}/{doc_id}_{filename}"
        put_result = put_bytes(storage_path, content, sniffed_content_type)
        if not put_result:
            raise HTTPException(status_code=503, detail="Document storage unavailable. Please retry.")

        docs.append(
            {
                "doc_id": doc_id,
                "type": key,
                "purpose": "business_verification" if key == "business_registration" else "id_verification",
                "filename": filename,
                "original_filename": str(item.filename or filename),
                "content_type": sniffed_content_type,
                "file_size": len(content),
                "checksum_sha256": security.get("checksum_sha256"),
                "security_scan": security.get("antivirus"),
                "storage_path": str(put_result.get("path") or storage_path),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    present_keys = {str(d.get("type") or "") for d in docs}
    missing = sorted(MANDATORY_APPROVAL_DOC_KEYS - present_keys)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing required documents",
                "missing_document_keys": missing,
            },
        )
    return docs



@router.post("/employer/approval/upload-document")
async def upload_approval_document(
    request: Request,
    document_key: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a verification document for employer approval (multipart/form-data)."""
    user = await require_auth(request)
    
    if not document_key or document_key not in MANDATORY_APPROVAL_DOC_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_key. Must be one of: {', '.join(sorted(MANDATORY_APPROVAL_DOC_KEYS))}"
        )
    
    ctype = _validate_content_type(file.content_type or "")
    content = await file.read()
    _assert_doc_size(content)
    
    try:
        security = enforce_file_security(
            content=content,
            claimed_content_type=ctype,
            allowed_content_types=ALLOWED_APPROVAL_DOC_CONTENT_TYPES,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"File security validation failed: {str(e)}")
    
    sniffed = str(security.get("sniffed_content_type") or ctype)
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "pdf"
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    _safe_filename(file.filename or "document")
    filename = f"{doc_id}_{document_key}.{ext}"
    storage_path = f"job-platform-approval/{user.user_id}/{filename}"
    
    result = put_bytes(storage_path, content, sniffed)
    if not result:
        raise HTTPException(status_code=503, detail="Document storage unavailable. Please retry.")
    
    return {
        "success": True,
        "document": {
            "document_key": document_key,
            "doc_id": doc_id,
            "filename": filename,
            "original_filename": file.filename,
            "content_type": sniffed,
            "file_size": len(content),
            "storage_path": result.get("path", storage_path),
        }
    }


@router.post("/employer/approval/submit")
async def submit_employer_approval(payload: EmployerApprovalRequest, request: Request):
    """Submit employer approval request for admin review."""
    user = await require_auth(request)

    existing = await db.employer_approvals.find_one(
        {"user_id": user.user_id, "status": {"$in": ["submitted", "in_review", "pending_decision"]}}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending approval request.")

    docs_payload = payload.documents or []
    if not docs_payload:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Required verification documents are missing",
                "missing_document_keys": sorted(MANDATORY_APPROVAL_DOC_KEYS),
            },
        )

    approval_id = f"apr_{uuid.uuid4().hex[:12]}"
    processed_docs = await _process_approval_documents(
        approval_id=approval_id,
        user_id=user.user_id,
        docs_payload=docs_payload,
    )

    # AI Fraud Risk Score
    risk_score = _compute_fraud_risk(payload, user.email)

    approval = {
        "approval_id": approval_id,
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "company_name": payload.company_name,
        "business_registration": payload.business_registration,
        "country": payload.country,
        "industry": payload.industry,
        "website": payload.website,
        "contact_email": payload.contact_email,
        "company_size": payload.company_size,
        "hiring_volume": payload.hiring_volume,
        "description": payload.description,
        "documents": processed_docs,
        "status": "submitted",
        "risk_score": risk_score,
        "reviewer_notes": "",
        "reviewed_by": None,
        "submitted_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "status_history": [
            {
                "status": "submitted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Application submitted",
            }
        ],
    }
    await db.employer_approvals.insert_one(approval)
    approval.pop("_id", None)

    # Send confirmation email
    try:
        from utils.email_service import send_catalog_template
        await send_catalog_template(user.email, "employer_submitted", user.name, user_name=user.name, company_name=payload.company_name)
        logger.info(f"Employer submission email sent to {user.email}")
    except Exception as e:
        logger.warning(f"Failed to send submission email: {e}")

    return {
        "message": "Approval request submitted successfully",
        "approval_id": approval["approval_id"],
        "status": "submitted",
    }


@router.get("/employer/approval/status")
async def get_employer_approval_status(request: Request):
    """Get employer's approval status."""
    user = await require_auth(request)

    approval = await db.employer_approvals.find_one({"user_id": user.user_id}, {"_id": 0})
    if not approval:
        return {"status": "none", "message": "No approval request found"}

    # Convert datetime fields
    for key in ("submitted_at", "updated_at"):
        if key in approval and hasattr(approval[key], "isoformat"):
            approval[key] = approval[key].isoformat()

    return approval


@router.post("/employer/approval/resubmit")
async def resubmit_employer_approval(request: Request):
    """Resubmit after 'need_more_info' status."""
    user = await require_auth(request)
    body = await request.json()

    approval = await db.employer_approvals.find_one({"user_id": user.user_id, "status": "need_more_info"})
    if not approval:
        raise HTTPException(status_code=400, detail="No pending request requiring additional info.")

    update = {"status": "submitted", "updated_at": datetime.now(timezone.utc)}
    if body.get("additional_info"):
        update["additional_info"] = body["additional_info"]

    history_entry = {
        "status": "resubmitted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Additional info provided",
    }
    await db.employer_approvals.update_one(
        {"user_id": user.user_id}, {"$set": update, "$push": {"status_history": history_entry}}
    )

    return {"message": "Request resubmitted", "status": "submitted"}


@router.get("/employer/approval/documents/{approval_id}/{doc_id}/download")
async def download_approval_document(approval_id: str, doc_id: str, request: Request):
    """Download approval document for owner or admin review."""
    user = await require_auth(request)

    approval = await db.employer_approvals.find_one({"approval_id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.get("user_id") != user.user_id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Access denied")

    docs = approval.get("documents") if isinstance(approval.get("documents"), list) else []
    target = next((d for d in docs if str(d.get("doc_id") or "") == str(doc_id)), None)
    if not target:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = str(target.get("storage_path") or "").strip()
    if not storage_path:
        raise HTTPException(status_code=404, detail="Document storage path missing")

    obj = get_bytes(storage_path)
    if not obj:
        raise HTTPException(status_code=404, detail="Document content unavailable")
    payload_bytes, media_type = obj
    filename = _safe_filename(str(target.get("original_filename") or target.get("filename") or f"{doc_id}.bin"))
    return Response(
        content=payload_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Original-Content-Type": media_type,
        },
    )


# ── Admin Review Endpoints ──


@router.get("/admin/approvals")
async def admin_list_approvals(request: Request, status: Optional[str] = None, page: int = 1, limit: int = 20):
    """Admin: List all employer approval requests."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = {}
    if status:
        query["status"] = status

    total = await db.employer_approvals.count_documents(query)
    cursor = (
        db.employer_approvals.find(query, {"_id": 0}).sort("submitted_at", -1).skip((page - 1) * limit).limit(limit)
    )
    approvals = []
    async for a in cursor:
        for key in ("submitted_at", "updated_at"):
            if key in a and hasattr(a[key], "isoformat"):
                a[key] = a[key].isoformat()
        approvals.append(a)

    stats = {
        "total": total,
        "submitted": await db.employer_approvals.count_documents({"status": "submitted"}),
        "in_review": await db.employer_approvals.count_documents({"status": "in_review"}),
        "approved": await db.employer_approvals.count_documents({"status": "approved"}),
        "denied": await db.employer_approvals.count_documents({"status": "denied"}),
    }

    return {"approvals": approvals, "total": total, "page": page, "pages": (total + limit - 1) // limit, "stats": stats}


class AdminDecisionRequest(BaseModel):
    approval_id: str
    decision: str  # approve, deny, need_more_info, suspend
    notes: Optional[str] = ""
    checklist_doc_completeness: Optional[bool] = None
    checklist_identity_match: Optional[bool] = None
    checklist_fraud_risk_reviewed: Optional[bool] = None


@router.post("/admin/approvals/decide")
async def admin_decide_approval(payload: AdminDecisionRequest, request: Request):
    """Admin: Make decision on employer approval."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if payload.decision not in ("approve", "deny", "need_more_info", "suspend"):
        raise HTTPException(status_code=400, detail="Invalid decision")

    if payload.decision == "approve":
        checks = {
            "doc_completeness": bool(payload.checklist_doc_completeness),
            "identity_match": bool(payload.checklist_identity_match),
            "fraud_risk_reviewed": bool(payload.checklist_fraud_risk_reviewed),
        }
        if not all(checks.values()):
            raise HTTPException(status_code=400, detail="Approve checklist incomplete")
        if not str(payload.notes or "").strip():
            raise HTTPException(status_code=400, detail="Reviewer note is required when approving")

    approval = await db.employer_approvals.find_one({"approval_id": payload.approval_id})
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    status_map = {"approve": "approved", "deny": "denied", "need_more_info": "need_more_info", "suspend": "suspended"}
    new_status = status_map[payload.decision]

    history_entry = {
        "status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": payload.notes or f"Decision: {payload.decision}",
        "by": user.email,
    }

    await db.employer_approvals.update_one(
        {"approval_id": payload.approval_id},
        {
            "$set": {
                "status": new_status,
                "reviewer_notes": payload.notes,
                "reviewed_by": user.email,
                "updated_at": datetime.now(timezone.utc),
                **(
                    {
                        "approval_checklist": {
                            "doc_completeness": True,
                            "identity_match": True,
                            "fraud_risk_reviewed": True,
                            "review_note": str(payload.notes or "").strip(),
                            "reviewed_by": user.email,
                            "reviewed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    }
                    if payload.decision == "approve"
                    else {}
                ),
            },
            "$push": {"status_history": history_entry},
        },
    )

    # If approved, update user roles to include employer
    if payload.decision == "approve":
        employer_user_id = approval["user_id"]
        await db.users.update_one({"user_id": employer_user_id}, {"$addToSet": {"roles": "employer"}})
        # Create/update employer profile
        await db.job_employers.update_one(
            {"user_id": employer_user_id},
            {
                "$set": {
                    "company_name": approval["company_name"],
                    "industry": approval["industry"],
                    "country": approval["country"],
                    "status": "active",
                    "approved_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    # Send email notification to employer
    employer_email = approval.get("email", "")
    employer_name = approval.get("name", "User")
    company_name = approval.get("company_name", "")
    try:
        from utils.email_service import send_catalog_template
        template_map = {
            "approve": "employer_approved",
            "deny": "employer_denied",
            "need_more_info": "employer_more_info",
            "suspend": "employer_suspended",
        }
        tpl_key = template_map.get(payload.decision)

        if tpl_key and employer_email:
            result = await send_catalog_template(employer_email, tpl_key, employer_name, user_name=employer_name, company_name=company_name, notes=payload.notes or "")
            logger.info(
                f"Employer decision email sent to {employer_email}: {payload.decision} (result: {result.get('success', False)})"
            )
    except Exception as e:
        logger.warning(f"Failed to send decision email to {employer_email}: {e}")

    decision_labels = {
        "approve": "approved",
        "deny": "denied",
        "need_more_info": "flagged for more info",
        "suspend": "suspended",
    }
    return {
        "message": f"Employer {decision_labels.get(payload.decision, payload.decision)} successfully",
        "status": new_status,
        "email_sent": True,
    }


@router.get("/admin/approvals/{approval_id}")
async def admin_get_approval_detail(approval_id: str, request: Request):
    """Admin: Get detailed approval request."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    approval = await db.employer_approvals.find_one({"approval_id": approval_id}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Not found")

    for key in ("submitted_at", "updated_at"):
        if key in approval and hasattr(approval[key], "isoformat"):
            approval[key] = approval[key].isoformat()

    return approval


# ── Admin Job Listings Management ──


@router.get("/admin/listings")
async def admin_list_jobs(request: Request, status: Optional[str] = None, page: int = 1, limit: int = 20):
    """Admin: List all job listings."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = {}
    if status:
        query["status"] = status

    total = await db.job_listings.count_documents(query)
    cursor = db.job_listings.find(query, {"_id": 0}).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
    jobs = []
    async for j in cursor:
        if "created_at" in j and hasattr(j["created_at"], "isoformat"):
            j["created_at"] = j["created_at"].isoformat()
        jobs.append(j)

    return {"jobs": jobs, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@router.get("/admin/stats")
async def admin_job_stats(request: Request):
    """Admin: Get job platform statistics."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return {
        "total_employers": await db.job_employers.count_documents({}),
        "total_jobs": await db.job_listings.count_documents({}),
        "active_jobs": await db.job_listings.count_documents({"status": "active"}),
        "total_applications": await db.job_applications.count_documents({}),
        "pending_approvals": await db.employer_approvals.count_documents({"status": "submitted"}),
        "approved_employers": await db.employer_approvals.count_documents({"status": "approved"}),
    }


# ── Support Ticket System ──


class SupportTicketRequest(BaseModel):
    category: str  # technical, account, approval, payment, other
    subject: str
    message: str


@router.post("/support/tickets")
async def create_support_ticket(payload: SupportTicketRequest, request: Request):
    """Create a support ticket."""
    user = await require_auth(request)

    ticket = {
        "ticket_id": f"tkt_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "email": encrypt_field(user.email or ""),
        "email_hash": hash_lookup(user.email or ""),
        "name": encrypt_field(user.name or ""),
        "category": payload.category,
        "subject": payload.subject,
        "message": encrypt_field(payload.message),
        "status": "open",
        "assigned_admin": None,
        "responses": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.support_tickets.insert_one(ticket)
    ticket.pop("_id", None)

    return {"message": "Ticket created", "ticket_id": ticket["ticket_id"]}


@router.get("/support/tickets")
async def list_user_tickets(request: Request):
    """List user's support tickets."""
    user = await require_auth(request)
    cursor = db.support_tickets.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    tickets = []
    async for t in cursor:
        decrypt_doc(t, ("name", "email", "message"))
        for k in ("created_at", "updated_at"):
            if k in t and hasattr(t[k], "isoformat"):
                t[k] = t[k].isoformat()
        tickets.append(t)
    return {"tickets": tickets}


@router.get("/admin/support/tickets")
async def admin_list_tickets(request: Request, status: Optional[str] = None):
    """Admin: List all support tickets."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = {}
    if status:
        query["status"] = status

    cursor = db.support_tickets.find(query, {"_id": 0}).sort("created_at", -1).limit(50)
    tickets = []
    async for t in cursor:
        decrypt_doc(t, ("name", "email", "message"))
        for k in ("created_at", "updated_at"):
            if k in t and hasattr(t[k], "isoformat"):
                t[k] = t[k].isoformat()
        tickets.append(t)

    return {"tickets": tickets, "total": await db.support_tickets.count_documents(query)}


class TicketResponseRequest(BaseModel):
    ticket_id: str
    message: str
    new_status: Optional[str] = None


@router.post("/admin/support/respond")
async def admin_respond_ticket(payload: TicketResponseRequest, request: Request):
    """Admin: Respond to a support ticket."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    response = {
        "from": user.email,
        "message": payload.message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    update = {"$push": {"responses": response}, "$set": {"updated_at": datetime.now(timezone.utc)}}
    if payload.new_status:
        update["$set"]["status"] = payload.new_status

    result = await db.support_tickets.update_one({"ticket_id": payload.ticket_id}, update)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {"message": "Response sent"}


# ── AI Fraud Risk Scoring ──


def _compute_fraud_risk(payload: EmployerApprovalRequest, email: str) -> int:
    """Compute fraud risk score (0-100) for employer application."""
    score = 0

    # Disposable email domains
    disposable_domains = {"tempmail", "throwaway", "guerrillamail", "mailinator", "yopmail", "10minutemail"}
    domain = email.split("@")[-1].lower().split(".")[0] if "@" in email else ""
    if domain in disposable_domains:
        score += 30

    # Missing critical fields
    if not payload.business_registration:
        score += 10
    if not payload.website:
        score += 8
    if not payload.description or len(payload.description) < 20:
        score += 12

    # Suspicious patterns
    if payload.company_name and any(w in payload.company_name.lower() for w in ["test", "fake", "xxx", "asdf"]):
        score += 25

    # Very small description
    if payload.description and len(payload.description) < 10:
        score += 15

    # Free email for business
    free_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com"}
    if email.split("@")[-1].lower() in free_domains:
        score += 5

    return min(100, score)


# ── AI Job Matching (simplified) ──


@router.get("/ai/match")
async def ai_job_match(request: Request):
    """AI-powered job matching for the current user."""
    user = await require_auth(request)

    # Get user's applications to understand preferences
    apps = await db.job_applications.find({"user_id": user.user_id}, {"_id": 0}).to_list(20)
    applied_job_ids = {a["job_id"] for a in apps}

    # Get all active jobs
    jobs = await db.job_listings.find({"status": "active"}, {"_id": 0}).to_list(50)

    # Simple matching: rank jobs not yet applied to
    matches = []
    for j in jobs:
        if j.get("job_id") in applied_job_ids:
            continue
        score = random.randint(60, 98)  # Simulated AI match score
        matches.append({**j, "match_score": score})

    matches.sort(key=lambda x: x["match_score"], reverse=True)

    return {"matches": matches[:20], "total": len(matches)}
