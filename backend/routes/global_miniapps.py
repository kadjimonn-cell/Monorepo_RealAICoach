from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path
import uuid
import os
import logging
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest
from utils.media_streaming import (
    get_media_path,
    stream_with_range,
    guess_mime_type,
    ensure_media_dirs,
    build_hls_manifest,
)
from utils.llm_helper import generate_verified_json
from utils.pdf_v15_filename import build_pdf_v15_filename
from .db import (
    db,
    require_auth,
    require_admin,
    sync_user_roles,
)
from .payments_catalog import get_subscription_plan_from_gps, get_subscription_plans_from_gps

router = APIRouter()
logger = logging.getLogger(__name__)


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")
    return themed

SMS_PENDING_MINUTES = 10

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")

MOBILE_MONEY_PROVIDERS = [
    {"id": "fedapay", "name": "FedaPay"},
]

EMPLOYER_PLANS = {
    "employer_basic": {
        "id": "employer_basic",
        "name": "Employer Basic",
        "monthly_price": 39.0,
        "yearly_price": 390.0,
        "features": [
            "Up to 10 active job posts",
            "AI ranking insights",
            "Applicant pipeline dashboard",
        ],
    },
    "employer_growth": {
        "id": "employer_growth",
        "name": "Employer Growth",
        "monthly_price": 89.0,
        "yearly_price": 890.0,
        "features": [
            "Unlimited job posts",
            "AI candidate matching",
            "Priority support",
        ],
    },
}

INVOICE_DIR = Path(__file__).parent.parent / "media" / "invoices"
INVOICE_DIR.mkdir(parents=True, exist_ok=True)


class EmployerProfileRequest(BaseModel):
    company_name: str
    company_logo: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None


class JobCreateRequest(BaseModel):
    title: str
    company_name: str
    company_logo: Optional[str] = None
    location: str
    remote: bool = False
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: str
    skills_required: List[str] = []
    category: str
    job_type: str


class JobUpdateRequest(BaseModel):
    title: Optional[str] = None
    company_name: Optional[str] = None
    company_logo: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[bool] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: Optional[str] = None
    skills_required: Optional[List[str]] = None
    category: Optional[str] = None
    job_type: Optional[str] = None
    status: Optional[str] = None


class JobApplicationRequest(BaseModel):
    job_id: str
    resume_text: Optional[str] = None
    resume_title: Optional[str] = None
    cover_letter: Optional[str] = None
    skills: List[str] = []


class ResumeCreateRequest(BaseModel):
    title: str
    summary: str
    experience: List[str] = []
    education: List[str] = []
    skills: List[str] = []
    certifications: List[str] = []
    projects: List[str] = []


class JobAIDescriptionRequest(BaseModel):
    job_title: str
    company_name: str
    location: Optional[str] = None
    seniority: Optional[str] = None
    context: Optional[str] = None


class JobAISalaryRequest(BaseModel):
    job_title: str
    location: str
    seniority: Optional[str] = None
    currency: str = "USD"


class MobileMoneyPaymentRequest(BaseModel):
    plan_id: str
    billing_period: str = "monthly"
    provider: str
    phone_number: str
    purpose: str = "user_subscription"
    currency: str = "USD"


class MobileMoneyCheckoutRequest(BaseModel):
    plan_id: str
    billing_period: str = "monthly"
    provider: str
    phone_number: str
    purpose: str = "user_subscription"
    currency: str = "USD"
    origin: str


class AccountingEntryRequest(BaseModel):
    title: str
    amount: float
    currency: str = "USD"
    category: Optional[str] = None
    date: Optional[str] = None
    notes: Optional[str] = None


class AccountingReportRequest(BaseModel):
    start_date: str
    end_date: str


class DramaUploadRequest(BaseModel):
    title: str
    description: str
    genre: str
    vertical: bool = True
    duration: Optional[int] = None


class MusicUploadRequest(BaseModel):
    title: str
    artist: str
    album: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[int] = None


class InvoiceItemRequest(BaseModel):
    description: str
    quantity: int
    unit_price: float


class InvoiceCreateRequest(BaseModel):
    client_id: str
    currency: str = "USD"
    due_date: Optional[str] = None
    items: List[InvoiceItemRequest]
    notes: Optional[str] = None


class ClientCreateRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class InvoiceAIGenerateRequest(BaseModel):
    client_name: str
    industry: str
    scope: str
    currency: str = "USD"


async def _add_user_role(user_id: str, role: str):
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        return
    roles = set(user_doc.get("roles", []) or [])
    roles.add(role)
    await db.users.update_one({"user_id": user_id}, {"$set": {"roles": sorted(roles)}})


async def _get_employer_profile(user_id: str):
    profile = await db.job_employers.find_one({"user_id": user_id}, {"_id": 0})
    if profile:
        return profile

    approved = await db.employer_applications.find_one(
        {"user_id": user_id, "status": "approved"},
        {"_id": 0, "employer_id": 1, "business_name": 1, "country": 1, "website": 1, "description": 1},
    )
    if not approved:
        return None

    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1},
    ) or {}

    synthesized = {
        "employer_id": approved.get("employer_id") or f"emp_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "company_name": approved.get("business_name") or "Approved Employer",
        "company_logo": None,
        "location": approved.get("country") or "",
        "website": approved.get("website") or "",
        "description": approved.get("description") or "",
        "subscription_plan": user_doc.get("subscription_plan") or "basic",
        "subscription_status": user_doc.get("subscription_status") or "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.job_employers.update_one({"user_id": user_id}, {"$set": synthesized}, upsert=True)
    await _add_user_role(user_id, "employer")
    return synthesized


def _normalize_job_for_portal(job: Dict[str, Any], source: str) -> Dict[str, Any]:
    normalized = {k: v for k, v in job.items() if k != "_id"}
    normalized["source"] = source
    if source == "jobs":
        normalized.setdefault("user_id", normalized.get("poster_user_id"))
        normalized.setdefault("skills_required", normalized.get("skills") or [])
        normalized.setdefault("category", normalized.get("industry") or "other")
    else:
        normalized.setdefault("poster_user_id", normalized.get("user_id"))
        normalized.setdefault("skills", normalized.get("skills_required") or [])
        normalized.setdefault("industry", normalized.get("category") or "")
    return normalized


def _job_matches_portal_filters(
    job: Dict[str, Any],
    q: Optional[str],
    location: Optional[str],
    country: Optional[str],
    category: Optional[str],
    job_type: Optional[str],
    remote: Optional[bool],
    salary_min: Optional[float],
    salary_max: Optional[float],
) -> bool:
    title = str(job.get("title") or "").lower()
    company = str(job.get("company_name") or "").lower()
    description = str(job.get("description") or "").lower()
    skills = [str(s).lower() for s in (job.get("skills_required") or job.get("skills") or [])]
    job_location = str(job.get("location") or "").lower()
    job_country = str(job.get("country") or "").lower()
    job_category = str(job.get("category") or job.get("industry") or "").lower()
    job_job_type = str(job.get("job_type") or "").lower()

    if q:
        needle = str(q).lower()
        searchable = " ".join([title, company, description, " ".join(skills)])
        if needle not in searchable:
            return False
    if location and str(location).lower() not in job_location:
        return False
    if country and str(country).lower() not in (job_country or job_location):
        return False
    if category and str(category).lower() != job_category:
        return False
    if job_type and str(job_type).lower() != job_job_type:
        return False
    if remote is not None and bool(job.get("remote")) != bool(remote):
        return False

    job_min = float(job.get("salary_min") or 0)
    job_max = float(job.get("salary_max") or 0)
    if salary_min is not None and job_max and job_max < float(salary_min):
        return False
    if salary_max is not None and job_min and job_min > float(salary_max):
        return False
    return True


async def _append_application_timeline_event(
    *,
    application_id: str,
    job_id: str,
    actor_user_id: str,
    event_type: str,
    title: str,
    description: str,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not application_id:
        return
    doc = {
        "event_id": f"apptl_{uuid.uuid4().hex[:14]}",
        "application_id": application_id,
        "job_id": job_id,
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "title": title,
        "description": description,
        "status": status,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.job_application_timeline_events.insert_one(doc)


async def _get_plan_amount(plan_id: str, billing_period: str):
    plan = await get_subscription_plan_from_gps(plan_id) or EMPLOYER_PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    price_key = "monthly_price" if billing_period == "monthly" else "yearly_price"
    return plan[price_key], plan


def _build_momo_sms(event: str, plan: dict, amount: float, currency: str) -> str:
    plan_name = plan.get("name", "Plan") if plan else "Plan"
    if event == "request_sent":
        return f"RealAICoach: Payment request sent for {plan_name} ({amount} {currency}). Approve on your phone."
    if event == "pending":
        return f"RealAICoach: Payment for {plan_name} is still pending after {SMS_PENDING_MINUTES} minutes. If approved, we will confirm soon."
    if event == "success":
        return f"RealAICoach: Payment confirmed. {plan_name} is now active. Thank you!"
    if event == "failed":
        return f"RealAICoach: Payment failed or timed out for {plan_name}. Please retry the Mobile Money checkout."
    return f"RealAICoach: Payment update for {plan_name}."


async def _send_payment_sms(
    payment_id: str, phone_number: str, message: str, flag_field: str, already_sent: bool = False
):
    if already_sent:
        return
    if not phone_number:
        return
    # SMS has been removed from this platform
    await db.mobile_money_payments.update_one(
        {"payment_id": payment_id},
        {"$set": {flag_field: False, f"{flag_field}_error": "SMS has been removed from this platform"}},
    )


async def _create_mobile_money_records(
    user,
    payload: dict,
    amount: float,
    plan: dict,
    payment_method: str,
    session_id: str | None = None,
    existing_payment: dict | None = None,
):
    existing = None
    if session_id:
        existing = await db.mobile_money_payments.find_one({"checkout_session_id": session_id}, {"_id": 0})
    if existing:
        return {
            "payment": existing,
            "transaction": None,
            "invoice": None,
            "subscription": None,
            "plan": plan,
        }

    payment = None
    payment_id = existing_payment.get("payment_id") if existing_payment else None
    if existing_payment:
        payment = {**existing_payment}
        payment_id = payment_id or f"pay_{uuid.uuid4().hex[:12]}"
        payment_update = {
            "status": "success",
            "payment_method": payment_method,
            "checkout_session_id": session_id,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.mobile_money_payments.update_one({"payment_id": payment_id}, {"$set": payment_update})
        payment.update(payment_update)
        payment["payment_id"] = payment_id
    else:
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        payment = {
            "payment_id": payment_id,
            "user_id": user.user_id,
            "plan_id": payload.get("plan_id"),
            "billing_period": payload.get("billing_period"),
            "provider": payload.get("provider"),
            "phone_number": payload.get("phone_number"),
            "amount": amount,
            "currency": payload.get("currency", "USD"),
            "purpose": payload.get("purpose", "user_subscription"),
            "status": "success",
            "payment_method": payment_method,
            "checkout_session_id": session_id,
            "sms_request_sent": False,
            "sms_pending_sent": False,
            "sms_success_sent": False,
            "sms_failed_sent": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.mobile_money_payments.insert_one(payment)
        payment.pop("_id", None)

    transaction = await db.mobile_money_transactions.find_one({"payment_id": payment_id}, {"_id": 0})
    if not transaction:
        transaction = {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "payment_id": payment_id,
            "provider": payload.get("provider"),
            "status": "confirmed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.mobile_money_transactions.insert_one(transaction)
        transaction.pop("_id", None)

    invoice = await db.mobile_money_invoices.find_one({"payment_id": payment_id}, {"_id": 0})
    if not invoice:
        invoice = {
            "invoice_id": f"inv_{uuid.uuid4().hex[:12]}",
            "payment_id": payment_id,
            "amount": amount,
            "currency": payload.get("currency", "USD"),
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.mobile_money_invoices.insert_one(invoice)
        invoice.pop("_id", None)

    subscription_payload = await db.mobile_money_subscriptions.find_one({"payment_id": payment_id}, {"_id": 0})
    if not subscription_payload:
        subscription_payload = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "payment_id": payment_id,
            "user_id": user.user_id,
            "plan_id": payload.get("plan_id"),
            "status": "active",
            "provider": payload.get("provider"),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "billing_period": payload.get("billing_period", "monthly"),
        }
        await db.mobile_money_subscriptions.insert_one(subscription_payload)
        subscription_payload.pop("_id", None)

    if payload.get("purpose") == "employer_subscription":
        employer = await _get_employer_profile(user.user_id)
        if employer:
            await db.job_employers.update_one(
                {"user_id": user.user_id},
                {
                    "$set": {
                        "subscription_plan": payload.get("plan_id"),
                        "subscription_status": "active",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            await _add_user_role(user.user_id, "employer")
    else:
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {"subscription_plan": payload.get("plan_id"), "subscription_status": "active"}},
        )
        user.subscription_plan = payload.get("plan_id")
        user.subscription_status = "active"
        await sync_user_roles(user)

    return {
        "payment": payment,
        "transaction": transaction,
        "invoice": invoice,
        "subscription": subscription_payload,
        "plan": plan,
    }


# ===========================
# Mini-App 1: Global AI Job Platform
# ===========================


@router.post("/jobs/employer/register")
async def register_employer(request: EmployerProfileRequest, req: Request):
    user = await require_auth(req)
    existing = await _get_employer_profile(user.user_id)
    payload = {
        "employer_id": existing.get("employer_id") if existing else f"emp_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "company_name": request.company_name,
        "company_logo": request.company_logo,
        "location": request.location,
        "website": request.website,
        "description": request.description,
        "subscription_plan": existing.get("subscription_plan", "employer_basic") if existing else "employer_basic",
        "subscription_status": existing.get("subscription_status", "inactive") if existing else "inactive",
        "created_at": existing.get("created_at", datetime.now(timezone.utc).isoformat())
        if existing
        else datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.job_employers.update_one({"user_id": user.user_id}, {"$set": payload}, upsert=True)
    await _add_user_role(user.user_id, "employer")
    return {"employer": payload}


@router.get("/jobs/employer/profile")
async def get_employer_profile(req: Request):
    user = await require_auth(req)
    profile = await _get_employer_profile(user.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Employer profile not found")
    return {"employer": profile}


@router.post("/jobs/create")
async def create_job(request: JobCreateRequest, req: Request):
    user = await require_auth(req)
    employer = await _get_employer_profile(user.user_id)
    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile required")
    if employer.get("subscription_status") != "active":
        raise HTTPException(status_code=403, detail="Employer subscription inactive")

    job_id = f"job_{uuid.uuid4().hex[:10]}"
    payload = {
        "job_id": job_id,
        "employer_id": employer["employer_id"],
        "user_id": user.user_id,
        "title": request.title,
        "company_name": request.company_name,
        "company_logo": request.company_logo,
        "location": request.location,
        "remote": request.remote,
        "salary_min": request.salary_min,
        "salary_max": request.salary_max,
        "description": request.description,
        "skills_required": request.skills_required,
        "category": request.category,
        "job_type": request.job_type,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.job_posts.insert_one(payload)
    payload.pop("_id", None)
    return {"job": payload}


@router.get("/jobs/employer/list")
async def list_employer_jobs(req: Request):
    user = await require_auth(req)
    jobs = await db.job_posts.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"jobs": jobs}


@router.put("/jobs/{job_id}")
async def update_job(job_id: str, request: JobUpdateRequest, req: Request):
    user = await require_auth(req)
    payload = {k: v for k, v in request.dict().items() if v is not None}
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.job_posts.update_one({"job_id": job_id, "user_id": user.user_id}, {"$set": payload})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    job = await db.job_posts.find_one({"job_id": job_id}, {"_id": 0})
    return {"job": job}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, req: Request):
    user = await require_auth(req)
    await db.job_posts.delete_one({"job_id": job_id, "user_id": user.user_id})
    return {"success": True}


@router.get("/jobs/search")
async def search_jobs(
    q: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    job_type: Optional[str] = None,
    remote: Optional[bool] = None,
    salary_min: Optional[float] = None,
    salary_max: Optional[float] = None,
    country: Optional[str] = None,
):
    job_posts = await db.job_posts.find({"status": "active"}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    core_jobs = await db.jobs.find({"status": "active"}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)

    normalized: List[Dict[str, Any]] = [
        *[_normalize_job_for_portal(j, "job_posts") for j in job_posts],
        *[_normalize_job_for_portal(j, "jobs") for j in core_jobs],
    ]

    jobs = [
        j
        for j in normalized
        if _job_matches_portal_filters(j, q, location, country, category, job_type, remote, salary_min, salary_max)
    ]
    jobs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {
        "jobs": jobs,
        "total": len(jobs),
        "filters_applied": {
            "q": q,
            "location": location,
            "country": country,
            "category": category,
            "job_type": job_type,
            "remote": remote,
            "salary_min": salary_min,
            "salary_max": salary_max,
        },
    }


@router.post("/jobs/apply")
async def apply_job(request: JobApplicationRequest, req: Request):
    user = await require_auth(req)
    job = await db.job_posts.find_one({"job_id": request.job_id}, {"_id": 0})
    source = "job_posts"
    if not job:
        job = await db.jobs.find_one({"job_id": request.job_id, "status": "active"}, {"_id": 0})
        source = "jobs" if job else ""
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    existing = await db.job_applications.find_one({"job_id": request.job_id, "user_id": user.user_id}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="You have already applied for this job")

    now_iso = datetime.now(timezone.utc).isoformat()
    application_id = f"app_{uuid.uuid4().hex[:10]}"
    payload = {
        "application_id": application_id,
        "job_id": request.job_id,
        "user_id": user.user_id,
        "candidate_id": user.user_id,
        "candidate_name": user.name,
        "candidate_email": user.email,
        "job_source": source,
        "employer_user_id": job.get("user_id") or job.get("poster_user_id"),
        "resume_text": request.resume_text,
        "resume_title": request.resume_title,
        "cover_letter": request.cover_letter,
        "skills": request.skills,
        "status": "applied",
        "created_at": now_iso,
        "applied_at": now_iso,
    }
    await db.job_applications.insert_one(payload)

    try:
        await _append_application_timeline_event(
            application_id=application_id,
            job_id=request.job_id,
            actor_user_id=user.user_id,
            event_type="application_submitted",
            title="Application Submitted",
            description=f"{user.name or 'Candidate'} submitted an application.",
            status="applied",
        )
    except Exception as e:
        logger.warning(f"jobs/apply timeline event failed: {e}")

    try:
        from routes.notification_engine import emit_notification

        candidate_name = getattr(user, "name", "Candidate")
        job_title = job.get("title") or "the selected role"
        await emit_notification(
            user_id=user.user_id,
            notif_type="job_application_submitted",
            title="Application Submitted",
            body=f"Your application for '{job_title}' has been submitted successfully.",
            action_url="/job-platform",
            metadata={"application_id": application_id, "job_id": request.job_id},
        )

        employer_user_id = job.get("user_id") or job.get("poster_user_id")
        employer_user = None
        if employer_user_id:
            employer_user = await db.users.find_one({"user_id": employer_user_id}, {"_id": 0, "user_id": 1})

        if employer_user_id and employer_user:
            await emit_notification(
                user_id=employer_user_id,
                notif_type="job_new_application",
                title="New Job Application",
                body=f"{candidate_name} applied for '{job_title}'.",
                action_url="/job-platform",
                metadata={"application_id": application_id, "job_id": request.job_id, "candidate_id": user.user_id},
            )
        else:
            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(10)
            for admin in admins:
                admin_id = admin.get("user_id")
                if not admin_id:
                    continue
                await emit_notification(
                    user_id=admin_id,
                    notif_type="job_new_application",
                    title="New Job Application",
                    body=f"{candidate_name} applied for '{job_title}'.",
                    action_url="/job-platform",
                    metadata={"application_id": application_id, "job_id": request.job_id, "candidate_id": user.user_id},
                )
    except Exception as e:
        logger.warning(f"jobs/apply notification dispatch failed: {e}")

    try:
        from utils.email_service import send_catalog_template

        role_title = job.get("title") or "Selected Role"
        await send_catalog_template(
            user.email,
            "career_status_received",
            user.name,
            applicant_name=user.name,
            role_title=role_title,
            application_id=application_id,
        )

        employer_user_id = job.get("user_id") or job.get("poster_user_id")
        if employer_user_id:
            employer_user = await db.users.find_one(
                {"user_id": employer_user_id},
                {"_id": 0, "email": 1, "name": 1},
            )
            if employer_user and employer_user.get("email"):
                await send_catalog_template(
                    employer_user.get("email"),
                    "career_admin_notify",
                    employer_user.get("name") or "Employer",
                    applicant_name=user.name,
                    position=role_title,
                    application_id=application_id,
                )
    except Exception as e:
        logger.warning(f"jobs/apply email dispatch failed: {e}")

    payload.pop("_id", None)
    return {"application": payload}


@router.get("/jobs/applications/user")
async def get_user_applications(req: Request):
    user = await require_auth(req)
    apps = await db.job_applications.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"applications": apps}


@router.get("/jobs/applications/employer")
async def get_employer_applications(req: Request, job_id: Optional[str] = None):
    user = await require_auth(req)
    employer = await _get_employer_profile(user.user_id)
    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile required")
    job_ids = set(
        job["job_id"]
        for job in await db.job_posts.find({"employer_id": employer["employer_id"]}, {"_id": 0, "job_id": 1}).to_list(200)
    )
    posted_jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1}).to_list(200)
    job_ids.update(j.get("job_id") for j in posted_jobs if j.get("job_id"))
    job_ids = list(job_ids)
    if job_id:
        job_ids = [job_id] if job_id in job_ids else []
    apps = await db.job_applications.find({"job_id": {"$in": job_ids}}, {"_id": 0}).sort("created_at", -1).to_list(300)
    return {"applications": apps}


@router.post("/jobs/save")
async def save_job(req: Request, job_id: str):
    user = await require_auth(req)
    exists = await db.job_saved.find_one({"user_id": user.user_id, "job_id": job_id})
    if exists:
        await db.job_saved.delete_one({"user_id": user.user_id, "job_id": job_id})
        return {"saved": False}
    await db.job_saved.insert_one(
        {"user_id": user.user_id, "job_id": job_id, "created_at": datetime.now(timezone.utc).isoformat()}
    )
    return {"saved": True}


@router.get("/jobs/saved")
async def get_saved_jobs(req: Request):
    user = await require_auth(req)
    saved = await db.job_saved.find({"user_id": user.user_id}, {"_id": 0}).to_list(200)
    job_ids = [s["job_id"] for s in saved]
    job_posts = await db.job_posts.find({"job_id": {"$in": job_ids}}, {"_id": 0}).to_list(200)
    core_jobs = await db.jobs.find({"job_id": {"$in": job_ids}}, {"_id": 0}).to_list(200)
    jobs = [
        *[_normalize_job_for_portal(j, "job_posts") for j in job_posts],
        *[_normalize_job_for_portal(j, "jobs") for j in core_jobs],
    ]
    # Keep both keys for strict backwards compatibility while standardizing contract.
    return {"saved_jobs": jobs, "jobs": jobs, "total": len(jobs)}


@router.post("/resumes/create")
async def create_resume(request: ResumeCreateRequest, req: Request):
    user = await require_auth(req)
    resume_id = f"res_{uuid.uuid4().hex[:10]}"
    payload = {
        "resume_id": resume_id,
        "user_id": user.user_id,
        "title": request.title,
        "summary": request.summary,
        "experience": request.experience,
        "education": request.education,
        "skills": request.skills,
        "certifications": request.certifications,
        "projects": request.projects,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.job_resumes.insert_one(payload)
    payload.pop("_id", None)
    return {"resume": payload}


@router.get("/resumes")
async def list_resumes(req: Request):
    user = await require_auth(req)
    resumes = await db.job_resumes.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"resumes": resumes}


@router.post("/resumes/ai/build")
async def ai_build_resume(request: ResumeCreateRequest, req: Request):
    user = await require_auth(req)
    prompt = f"""Create a professional resume in JSON format.
Name: {user.name}
Summary: {request.summary}
Experience: {request.experience}
Education: {request.education}
Skills: {request.skills}
Certifications: {request.certifications}
Projects: {request.projects}
Return JSON with fields: title, summary, experience, education, skills, certifications, projects, ai_suggestions."""
    result = await generate_verified_json(prompt, "You are an expert resume writer.", f"resume-build-{uuid.uuid4()}")
    resume_id = f"res_{uuid.uuid4().hex[:10]}"
    payload = {
        "resume_id": resume_id,
        "user_id": user.user_id,
        "title": result.get("title") or request.title,
        "summary": result.get("summary") or request.summary,
        "experience": result.get("experience") or request.experience,
        "education": result.get("education") or request.education,
        "skills": result.get("skills") or request.skills,
        "certifications": result.get("certifications") or request.certifications,
        "projects": result.get("projects") or request.projects,
        "ai_suggestions": result.get("ai_suggestions", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.job_resumes.insert_one(payload)
    payload.pop("_id", None)
    return {"resume": payload}


@router.post("/resumes/ai/analyze")
async def ai_analyze_resume(req: Request, resume_text: str = Form(...)):
    await require_auth(req)
    prompt = f"""Analyze this resume and provide strengths, gaps, and improvement tips.
Resume: {resume_text}
Return JSON: strengths[], gaps[], improvements[], overall_score."""
    result = await generate_verified_json(prompt, "You are a senior recruiter.", f"resume-analyze-{uuid.uuid4()}")
    return {"analysis": result}


@router.post("/jobs/ai/description")
async def ai_job_description(request: JobAIDescriptionRequest, req: Request):
    await require_auth(req)
    prompt = f"""Generate a detailed job description.
Title: {request.job_title}
Company: {request.company_name}
Location: {request.location}
Seniority: {request.seniority}
Context: {request.context}
Return JSON with description, responsibilities[], requirements[], benefits[], skills[]."""
    result = await generate_verified_json(prompt, "You are a world-class hiring manager.", f"job-desc-{uuid.uuid4()}")
    return {"job_description": result}


@router.post("/jobs/ai/salary")
async def ai_salary_recommendation(request: JobAISalaryRequest, req: Request):
    await require_auth(req)
    prompt = f"""Estimate a competitive salary range for the role.
Title: {request.job_title}
Location: {request.location}
Seniority: {request.seniority}
Currency: {request.currency}
Return JSON with min, max, median, rationale."""
    result = await generate_verified_json(prompt, "You are a compensation analyst.", f"salary-{uuid.uuid4()}")
    return {"salary": result}


@router.post("/jobs/ai/rank-candidates")
async def ai_rank_candidates(req: Request, job_id: str = Form(...)):
    await require_auth(req)
    job = await db.job_posts.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    candidates = await db.job_applications.find({"job_id": job_id}, {"_id": 0}).to_list(200)
    prompt = f"""Rank candidates for this job based on skills and resume content.
Job: {job}
Candidates: {candidates}
Return JSON list of {{application_id, score, summary}} sorted by score descending."""
    try:
        result = await generate_verified_json(prompt, "You are an expert recruiter.", f"rank-{uuid.uuid4()}")
        return {"rankings": result}
    except Exception:
        # fallback: simple skill overlap
        required = set([s.lower() for s in job.get("skills_required", [])])
        ranked = []
        for cand in candidates:
            cand_skills = set([s.lower() for s in cand.get("skills", [])])
            score = round(len(required.intersection(cand_skills)) / max(len(required), 1) * 100, 1)
            ranked.append({"application_id": cand.get("application_id"), "score": score, "summary": "Auto-match score"})
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return {"rankings": ranked}


@router.post("/jobs/ai/match")
async def ai_match_job(req: Request, job_id: str = Form(...), resume_text: str = Form(...)):
    await require_auth(req)
    job = await db.job_posts.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    prompt = f"""Evaluate candidate fit for this job.
Job: {job}
Resume: {resume_text}
Return JSON with match_score (0-100), strengths[], gaps[], recommendation."""
    result = await generate_verified_json(prompt, "You are a recruitment AI.", f"match-{uuid.uuid4()}")
    return {"match": result}


@router.post("/jobs/ai/recommendations")
async def ai_job_recommendations(req: Request, resume_text: str = Form(...)):
    await require_auth(req)
    jobs = await db.job_posts.find({"status": "active"}, {"_id": 0}).limit(50).to_list(50)
    prompt = f"""Recommend the top 5 job_ids for this resume.
Resume: {resume_text}
Jobs: {jobs}
Return JSON list of {{job_id, reason}}."""
    result = await generate_verified_json(prompt, "You are a job matching assistant.", f"job-reco-{uuid.uuid4()}")
    return {"recommendations": result}


# ===========================
# Mini-App 2: Mobile Money Subscription System
# ===========================


@router.get("/mobile-money/providers")
async def list_mobile_money_providers():
    return {"providers": MOBILE_MONEY_PROVIDERS}


@router.get("/mobile-money/plans")
async def list_mobile_money_plans():
    gps_plans = await get_subscription_plans_from_gps()
    plans = [{**plan, "plan_id": key} for key, plan in gps_plans.items()] + [
        {**plan, "plan_id": key} for key, plan in EMPLOYER_PLANS.items()
    ]
    return {"plans": plans}


@router.post("/mobile-money/checkout/session")
async def create_mobile_money_checkout(request: MobileMoneyCheckoutRequest, req: Request):
    user = await require_auth(req)
    if request.provider not in [p["id"] for p in MOBILE_MONEY_PROVIDERS]:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    amount, plan = await _get_plan_amount(request.plan_id, request.billing_period)
    origin = (request.origin or req.headers.get("origin") or str(req.base_url)).rstrip("/")
    webhook_url = f"{str(req.base_url).rstrip('/')}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    checkout_req = CheckoutSessionRequest(
        amount=float(amount),
        currency=request.currency.lower(),
        success_url=f"{origin}/mini-apps/mobile-money?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/mini-apps/mobile-money?status=cancelled",
        metadata={
            "user_id": user.user_id,
            "plan_id": request.plan_id,
            "billing_period": request.billing_period,
            "provider": request.provider,
            "phone_number": request.phone_number,
            "purpose": request.purpose,
            "currency": request.currency,
            "flow": "mobile_money",
        },
        payment_methods=["card"],
    )
    session = await stripe_checkout.create_checkout_session(checkout_req)

    await db.payment_transactions.insert_one(
        {
            "session_id": session.session_id,
            "user_id": user.user_id,
            "plan_id": request.plan_id,
            "billing_period": request.billing_period,
            "provider": request.provider,
            "phone_number": request.phone_number,
            "amount": amount,
            "currency": request.currency,
            "purpose": request.purpose,
            "payment_method": "stripe_mobile_money",
            "payment_status": "initiated",
            "source": "mobile_money",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return {
        "checkout_url": session.url,
        "session_id": session.session_id,
        "plan": plan,
    }


@router.get("/mobile-money/checkout/status/{session_id}")
async def get_mobile_money_checkout_status(session_id: str, req: Request):
    user = await require_auth(req)
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    status = await stripe_checkout.get_checkout_status(session_id)

    txn = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if txn and txn.get("user_id") != user.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    if txn and status.payment_status == "paid" and txn.get("payment_status") != "completed":
        payload = {
            "plan_id": txn.get("plan_id"),
            "billing_period": txn.get("billing_period", "monthly"),
            "provider": txn.get("provider"),
            "phone_number": txn.get("phone_number"),
            "purpose": txn.get("purpose", "user_subscription"),
            "currency": txn.get("currency", "USD"),
        }
        amount, plan = await _get_plan_amount(payload["plan_id"], payload["billing_period"])
        records = await _create_mobile_money_records(
            user, payload, amount, plan, payment_method="stripe_mobile_money", session_id=session_id
        )
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"status": status.payment_status, "records": records}

    if txn:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": status.payment_status, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )

    return {"status": status.payment_status}


@router.post("/mobile-money/process")
async def process_mobile_money(request: MobileMoneyPaymentRequest, req: Request):
    user = await require_auth(req)
    if request.provider not in [p["id"] for p in MOBILE_MONEY_PROVIDERS]:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    amount, plan = await _get_plan_amount(request.plan_id, request.billing_period)
    payload = request.dict()

    records = await _create_mobile_money_records(user, payload, amount, plan, payment_method="internal_simulation")
    payment = records.get("payment") if isinstance(records, dict) else None
    if payment:
        await _send_payment_sms(
            payment.get("payment_id"),
            payment.get("phone_number"),
            _build_momo_sms("request_sent", plan, amount, payment.get("currency", "USD")),
            "sms_request_sent",
            payment.get("sms_request_sent", False),
        )
        await _send_payment_sms(
            payment.get("payment_id"),
            payment.get("phone_number"),
            _build_momo_sms("success", plan, amount, payment.get("currency", "USD")),
            "sms_success_sent",
            payment.get("sms_success_sent", False),
        )
    return {**records, "status": "success"}


@router.get("/mobile-money/status/{reference_id}")
async def get_mobile_money_status(reference_id: str, req: Request):
    user = await require_auth(req)
    payment = await db.mobile_money_payments.find_one(
        {"provider_reference": reference_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")

    created_at = payment.get("created_at")
    if created_at:
        try:
            datetime.fromisoformat(created_at)
        except ValueError:
            pass

    if payment.get("status") == "success":
        transaction = await db.mobile_money_transactions.find_one({"payment_id": payment.get("payment_id")}, {"_id": 0})
        invoice = await db.mobile_money_invoices.find_one({"payment_id": payment.get("payment_id")}, {"_id": 0})
        subscription = await db.mobile_money_subscriptions.find_one(
            {"payment_id": payment.get("payment_id")}, {"_id": 0}
        )
        amount, plan = await _get_plan_amount(payment.get("plan_id"), payment.get("billing_period", "monthly"))
        return {
            "status": "success",
            "payment": payment,
            "transaction": transaction,
            "invoice": invoice,
            "subscription": subscription,
            "plan": plan,
        }

    return {"status": payment.get("status", "pending"), "payment": payment}


@router.get("/mobile-money/transactions")
async def list_mobile_money_transactions(req: Request):
    user = await require_auth(req)
    payments = (
        await db.mobile_money_payments.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    )
    return {"payments": payments}


# ===========================
# Mini-App 3: AI Accounting System
# ===========================


@router.post("/accounting/income")
async def add_income(request: AccountingEntryRequest, req: Request):
    user = await require_auth(req)
    entry = {
        "income_id": f"inc_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "title": request.title,
        "amount": request.amount,
        "currency": request.currency,
        "category": request.category,
        "date": request.date or datetime.now(timezone.utc).date().isoformat(),
        "notes": request.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.accounting_income.insert_one(entry)
    entry.pop("_id", None)
    return {"income": entry}


@router.get("/accounting/income")
async def list_income(req: Request):
    user = await require_auth(req)
    items = await db.accounting_income.find({"user_id": user.user_id}, {"_id": 0}).sort("date", -1).to_list(200)
    return {"income": items}


@router.post("/accounting/expenses")
async def add_expense(request: AccountingEntryRequest, req: Request):
    user = await require_auth(req)
    entry = {
        "expense_id": f"exp_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "title": request.title,
        "amount": request.amount,
        "currency": request.currency,
        "category": request.category,
        "date": request.date or datetime.now(timezone.utc).date().isoformat(),
        "notes": request.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.accounting_expenses.insert_one(entry)
    entry.pop("_id", None)
    return {"expense": entry}


@router.get("/accounting/expenses")
async def list_expenses(req: Request):
    user = await require_auth(req)
    items = await db.accounting_expenses.find({"user_id": user.user_id}, {"_id": 0}).sort("date", -1).to_list(200)
    return {"expenses": items}


@router.get("/accounting/summary")
async def accounting_summary(req: Request):
    user = await require_auth(req)
    incomes = await db.accounting_income.find({"user_id": user.user_id}, {"_id": 0}).to_list(1000)
    expenses = await db.accounting_expenses.find({"user_id": user.user_id}, {"_id": 0}).to_list(1000)
    total_income = sum(i.get("amount", 0) for i in incomes)
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_profit": total_income - total_expenses,
    }


@router.post("/accounting/report")
async def generate_report(request: AccountingReportRequest, req: Request):
    user = await require_auth(req)
    report_id = f"rep_{uuid.uuid4().hex[:10]}"
    report = {
        "report_id": report_id,
        "user_id": user.user_id,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.accounting_reports.insert_one(report)
    report.pop("_id", None)
    return {"report": report}


@router.get("/accounting/reports")
async def list_reports(req: Request):
    user = await require_auth(req)
    reports = (
        await db.accounting_reports.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    )
    return {"reports": reports}


@router.post("/accounting/ai/insights")
async def accounting_insights(req: Request):
    user = await require_auth(req)
    incomes = await db.accounting_income.find({"user_id": user.user_id}, {"_id": 0}).to_list(200)
    expenses = await db.accounting_expenses.find({"user_id": user.user_id}, {"_id": 0}).to_list(200)
    prompt = f"""Provide financial insights based on income and expenses.
Income: {incomes}
Expenses: {expenses}
Return JSON with insights[], risks[], recommendations[], profit_outlook."""
    result = await generate_verified_json(prompt, "You are a CFO advisor.", f"acct-insight-{uuid.uuid4()}")
    return {"insights": result}


@router.post("/accounting/ai/profit-forecast")
async def profit_forecast(req: Request):
    user = await require_auth(req)
    incomes = await db.accounting_income.find({"user_id": user.user_id}, {"_id": 0}).to_list(200)
    expenses = await db.accounting_expenses.find({"user_id": user.user_id}, {"_id": 0}).to_list(200)
    prompt = f"""Predict next month's profit based on trends.
Income: {incomes}
Expenses: {expenses}
Return JSON with forecast_amount, confidence, drivers[]."""
    result = await generate_verified_json(prompt, "You are a financial forecaster.", f"acct-forecast-{uuid.uuid4()}")
    return {"forecast": result}


# ===========================
# Mini-App 4: AI Drama Box
# ===========================


@router.get("/drama/list")
async def list_drama():
    dramas = await db.drama_videos.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"dramas": dramas}


@router.post("/drama/upload")
async def upload_drama(
    req: Request,
    title: str = Form(...),
    description: str = Form(...),
    genre: str = Form(...),
    file: UploadFile = File(...),
):
    await require_admin(req)
    ensure_media_dirs()
    drama_id = f"drama_{uuid.uuid4().hex[:10]}"
    file_name = f"{drama_id}_{file.filename}"
    file_path = get_media_path("video", file_name)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    payload = {
        "drama_id": drama_id,
        "title": title,
        "description": description,
        "genre": genre,
        "file_name": file_name,
        "stream_url": f"/api/drama/stream/{drama_id}",
        "hls_url": f"/api/drama/hls/{drama_id}.m3u8",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.drama_videos.insert_one(payload)
    payload.pop("_id", None)
    return {"drama": payload}


@router.get("/drama/stream/{drama_id}")
async def stream_drama(drama_id: str, req: Request):
    drama = await db.drama_videos.find_one({"drama_id": drama_id}, {"_id": 0})
    if not drama:
        raise HTTPException(status_code=404, detail="Drama not found")
    file_path = get_media_path("video", drama.get("file_name"))
    return stream_with_range(req, file_path, guess_mime_type(file_path, "video/mp4"))


@router.get("/drama/hls/{drama_id}.m3u8")
async def drama_hls_manifest(drama_id: str):
    drama = await db.drama_videos.find_one({"drama_id": drama_id}, {"_id": 0})
    if not drama:
        raise HTTPException(status_code=404, detail="Drama not found")
    stream_url = f"/api/drama/stream/{drama_id}"
    manifest = build_hls_manifest(stream_url, drama.get("duration", 60))
    return Response(manifest, media_type="application/vnd.apple.mpegurl")


@router.post("/drama/history")
async def add_drama_history(req: Request, drama_id: str = Form(...), progress_seconds: int = Form(0)):
    user = await require_auth(req)
    entry = {
        "user_id": user.user_id,
        "drama_id": drama_id,
        "progress_seconds": progress_seconds,
        "watched_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.drama_history.insert_one(entry)
    return {"success": True}


@router.get("/drama/history")
async def list_drama_history(req: Request):
    user = await require_auth(req)
    history = await db.drama_history.find({"user_id": user.user_id}, {"_id": 0}).sort("watched_at", -1).to_list(100)
    return {"history": history}


@router.post("/drama/favorites/toggle")
async def toggle_drama_favorite(req: Request, drama_id: str = Form(...)):
    user = await require_auth(req)
    existing = await db.drama_favorites.find_one({"user_id": user.user_id, "drama_id": drama_id})
    if existing:
        await db.drama_favorites.delete_one({"user_id": user.user_id, "drama_id": drama_id})
        return {"favorite": False}
    await db.drama_favorites.insert_one(
        {"user_id": user.user_id, "drama_id": drama_id, "created_at": datetime.now(timezone.utc).isoformat()}
    )
    return {"favorite": True}


@router.get("/drama/favorites")
async def list_drama_favorites(req: Request):
    user = await require_auth(req)
    favs = await db.drama_favorites.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)
    drama_ids = [f["drama_id"] for f in favs]
    dramas = await db.drama_videos.find({"drama_id": {"$in": drama_ids}}, {"_id": 0}).to_list(100)
    return {"favorites": dramas}


@router.get("/drama/recommendations")
async def drama_recommendations(req: Request):
    user = await require_auth(req)
    history = (
        await db.drama_history.find({"user_id": user.user_id}, {"_id": 0}).sort("watched_at", -1).limit(10).to_list(10)
    )
    dramas = await db.drama_videos.find({}, {"_id": 0}).limit(50).to_list(50)
    prompt = f"""Recommend 5 dramas based on watch history.
History: {history}
Catalog: {dramas}
Return JSON list of {{drama_id, reason}}."""
    result = await generate_verified_json(prompt, "You are a drama recommendation AI.", f"drama-reco-{uuid.uuid4()}")
    return {"recommendations": result}


# ===========================
# Mini-App 5: AI Music Streaming
# ===========================


@router.get("/music/songs")
async def list_songs():
    songs = await db.music_songs.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"songs": songs}


@router.post("/music/upload")
async def upload_song(
    req: Request, title: str = Form(...), artist: str = Form(...), genre: str = Form(""), file: UploadFile = File(...)
):
    await require_admin(req)
    ensure_media_dirs()
    song_id = f"song_{uuid.uuid4().hex[:10]}"
    file_name = f"{song_id}_{file.filename}"
    file_path = get_media_path("audio", file_name)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    payload = {
        "song_id": song_id,
        "title": title,
        "artist": artist,
        "genre": genre,
        "file_name": file_name,
        "stream_url": f"/api/music/stream/{song_id}",
        "hls_url": f"/api/music/hls/{song_id}.m3u8",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.music_songs.insert_one(payload)
    payload.pop("_id", None)
    return {"song": payload}


@router.get("/music/stream/{song_id}")
async def stream_song(song_id: str, req: Request):
    song = await db.music_songs.find_one({"song_id": song_id}, {"_id": 0})
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    file_path = get_media_path("audio", song.get("file_name"))
    return stream_with_range(req, file_path, guess_mime_type(file_path, "audio/mpeg"))


@router.get("/music/hls/{song_id}.m3u8")
async def music_hls_manifest(song_id: str):
    song = await db.music_songs.find_one({"song_id": song_id}, {"_id": 0})
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    stream_url = f"/api/music/stream/{song_id}"
    manifest = build_hls_manifest(stream_url, song.get("duration", 60))
    return Response(manifest, media_type="application/vnd.apple.mpegurl")


@router.post("/music/history")
async def add_music_history(req: Request, song_id: str = Form(...)):
    user = await require_auth(req)
    entry = {
        "user_id": user.user_id,
        "song_id": song_id,
        "played_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.music_history.insert_one(entry)
    return {"success": True}


@router.get("/music/history")
async def list_music_history(req: Request):
    user = await require_auth(req)
    history = await db.music_history.find({"user_id": user.user_id}, {"_id": 0}).sort("played_at", -1).to_list(100)
    return {"history": history}


@router.post("/music/playlists")
async def create_playlist(req: Request, name: str = Form(...)):
    user = await require_auth(req)
    playlist = {
        "playlist_id": f"pl_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "name": name,
        "song_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.music_playlists.insert_one(playlist)
    playlist.pop("_id", None)
    return {"playlist": playlist}


@router.get("/music/playlists")
async def list_playlists(req: Request):
    user = await require_auth(req)
    playlists = await db.music_playlists.find({"user_id": user.user_id}, {"_id": 0}).to_list(50)
    return {"playlists": playlists}


@router.post("/music/playlists/{playlist_id}/songs")
async def add_song_to_playlist(playlist_id: str, req: Request, song_id: str = Form(...)):
    user = await require_auth(req)
    await db.music_playlists.update_one(
        {"playlist_id": playlist_id, "user_id": user.user_id},
        {"$addToSet": {"song_ids": song_id}},
    )
    playlist = await db.music_playlists.find_one({"playlist_id": playlist_id}, {"_id": 0})
    return {"playlist": playlist}


@router.get("/music/recommendations")
async def music_recommendations(req: Request):
    user = await require_auth(req)
    history = (
        await db.music_history.find({"user_id": user.user_id}, {"_id": 0}).sort("played_at", -1).limit(10).to_list(10)
    )
    songs = await db.music_songs.find({}, {"_id": 0}).limit(50).to_list(50)
    prompt = f"""Recommend 5 songs based on listening history.
History: {history}
Catalog: {songs}
Return JSON list of {{song_id, reason}}."""
    result = await generate_verified_json(prompt, "You are a music recommendation AI.", f"music-reco-{uuid.uuid4()}")
    return {"recommendations": result}


# ===========================
# Mini-App 6: AI Local Music Player
# ===========================


@router.post("/local-music/upload")
async def upload_local_music(
    req: Request, title: str = Form(...), artist: str = Form(...), file: UploadFile = File(...)
):
    user = await require_auth(req)
    ensure_media_dirs()
    track_id = f"track_{uuid.uuid4().hex[:10]}"
    file_name = f"{track_id}_{file.filename}"
    file_path = get_media_path("audio", file_name)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    payload = {
        "track_id": track_id,
        "user_id": user.user_id,
        "title": title,
        "artist": artist,
        "file_name": file_name,
        "stream_url": f"/api/local-music/stream/{track_id}",
        "hls_url": f"/api/local-music/hls/{track_id}.m3u8",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.local_music.insert_one(payload)
    payload.pop("_id", None)
    await _add_user_role(user.user_id, "creator")
    return {"track": payload}


@router.get("/local-music/stream/{track_id}")
async def stream_local_music(track_id: str, req: Request):
    track = await db.local_music.find_one({"track_id": track_id}, {"_id": 0})
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    file_path = get_media_path("audio", track.get("file_name"))
    return stream_with_range(req, file_path, guess_mime_type(file_path, "audio/mpeg"))


@router.get("/local-music/hls/{track_id}.m3u8")
async def local_music_hls_manifest(track_id: str):
    track = await db.local_music.find_one({"track_id": track_id}, {"_id": 0})
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    stream_url = f"/api/local-music/stream/{track_id}"
    manifest = build_hls_manifest(stream_url, track.get("duration", 60))
    return Response(manifest, media_type="application/vnd.apple.mpegurl")


@router.get("/local-music/tracks")
async def list_local_tracks(req: Request):
    user = await require_auth(req)
    tracks = await db.local_music.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"tracks": tracks}


@router.post("/local-music/library")
async def create_local_library(req: Request, name: str = Form(...)):
    user = await require_auth(req)
    library = {
        "library_id": f"lib_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "name": name,
        "track_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.local_music_libraries.insert_one(library)
    library.pop("_id", None)
    return {"library": library}


@router.get("/local-music/library")
async def list_local_libraries(req: Request):
    user = await require_auth(req)
    libraries = await db.local_music_libraries.find({"user_id": user.user_id}, {"_id": 0}).to_list(50)
    return {"libraries": libraries}


@router.post("/local-music/library/{library_id}/tracks")
async def add_track_to_library(library_id: str, req: Request, track_id: str = Form(...)):
    user = await require_auth(req)
    await db.local_music_libraries.update_one(
        {"library_id": library_id, "user_id": user.user_id},
        {"$addToSet": {"track_ids": track_id}},
    )
    library = await db.local_music_libraries.find_one({"library_id": library_id}, {"_id": 0})
    return {"library": library}


# ===========================
# Mini-App 7: AI Invoice Generator
# ===========================


@router.post("/clients/create")
async def create_client(request: ClientCreateRequest, req: Request):
    user = await require_auth(req)
    client = {
        "client_id": f"client_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "name": request.name,
        "email": request.email,
        "phone": request.phone,
        "address": request.address,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.invoice_clients.insert_one(client)
    client.pop("_id", None)
    return {"client": client}


@router.get("/clients")
async def list_clients(req: Request):
    user = await require_auth(req)
    clients = await db.invoice_clients.find({"user_id": user.user_id}, {"_id": 0}).to_list(200)
    return {"clients": clients}


@router.post("/invoices/create")
async def create_invoice(request: InvoiceCreateRequest, req: Request):
    user = await require_auth(req)
    invoice_id = f"inv_{uuid.uuid4().hex[:10]}"
    items = []
    total = 0
    for item in request.items:
        item_total = item.quantity * item.unit_price
        total += item_total
        items.append(
            {
                "item_id": f"item_{uuid.uuid4().hex[:8]}",
                "invoice_id": invoice_id,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total": item_total,
            }
        )
    invoice = {
        "invoice_id": invoice_id,
        "user_id": user.user_id,
        "client_id": request.client_id,
        "currency": request.currency,
        "total": total,
        "status": "draft",
        "due_date": request.due_date,
        "notes": request.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.invoices.insert_one(invoice)
    if items:
        await db.invoice_items.insert_many(items)
    invoice.pop("_id", None)
    # Remove _id from all items (insert_many adds _id to each dict)
    for item in items:
        item.pop("_id", None)
    return {"invoice": invoice, "items": items}


@router.get("/invoices")
async def list_invoices(req: Request):
    user = await require_auth(req)
    invoices = await db.invoices.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"invoices": invoices}


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, req: Request):
    user = await require_auth(req)
    invoice = await db.invoices.find_one({"invoice_id": invoice_id, "user_id": user.user_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    items = await db.invoice_items.find({"invoice_id": invoice_id}, {"_id": 0}).to_list(200)
    return {"invoice": invoice, "items": items}


def _render_invoice_pdf(invoice: dict, items: list, client: dict | None):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    file_path = INVOICE_DIR / f"{invoice['invoice_id']}.pdf"
    c = canvas.Canvas(str(file_path), pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, height - 40, "RealAICoach Invoice")
    c.setFont("Helvetica", 11)
    c.drawString(40, height - 70, f"Invoice ID: {invoice['invoice_id']}")
    c.drawString(40, height - 90, f"Date: {invoice['created_at'][:10]}")
    if client:
        c.drawString(40, height - 120, f"Billed To: {client.get('name')}")
        c.drawString(40, height - 140, f"Email: {client.get('email', '')}")
    y = height - 180
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(340, y, "Unit")
    c.drawString(420, y, "Total")
    c.setFont("Helvetica", 11)
    y -= 20
    for item in items:
        c.drawString(40, y, item.get("description"))
        c.drawString(300, y, str(item.get("quantity")))
        c.drawString(340, y, f"{item.get('unit_price'):.2f}")
        c.drawString(420, y, f"{item.get('total'):.2f}")
        y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y - 10, f"Total: {invoice['total']:.2f} {invoice['currency']}")
    c.save()

    raw_bytes = file_path.read_bytes()
    composed = compose_pdf_v15_helper_layout(
        raw_bytes,
        title="Invoice Document",
        subtitle="Mini Apps billing export",
        right_primary=f"Invoice: {invoice.get('invoice_id')}",
        right_secondary=f"Total {invoice.get('currency')} {invoice.get('total')}",
        badge_text="INVOICE OPERATIONS",
        badge_status="PASS",
        footer_text="RealAICoach Mini Apps • Enterprise profile",
        summary_title="Invoice Snapshot",
        summary_rows=[
            ("Line Items", str(len(items))),
            ("Client", (client or {}).get("name") or "N/A"),
            ("Issued", str(invoice.get("created_at", ""))[:10]),
        ],
        callout_title="Payment Context",
        callout_subtitle="Client billing package",
        callout_detail="Invoice includes line-level charges with canonical v15 governance overlays.",
        callout_status="PASS",
    )
    enforced = _enforce_pdf_v15_enterprise(composed, f"miniapps_invoice_{invoice.get('invoice_id')}")
    file_path.write_bytes(enforced)
    return file_path


@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, req: Request):
    user = await require_auth(req)
    invoice = await db.invoices.find_one({"invoice_id": invoice_id, "user_id": user.user_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    items = await db.invoice_items.find({"invoice_id": invoice_id}, {"_id": 0}).to_list(200)
    client = await db.invoice_clients.find_one({"client_id": invoice.get("client_id")}, {"_id": 0})
    file_path = _render_invoice_pdf(invoice, items, client)
    return FileResponse(file_path, media_type="application/pdf", filename=build_pdf_v15_filename("invoice", invoice_id))


@router.post("/invoices/ai/generate")
async def ai_generate_invoice(request: InvoiceAIGenerateRequest, req: Request):
    await require_auth(req)
    prompt = f"""Generate invoice line items for the following scope.
Client: {request.client_name}
Industry: {request.industry}
Scope: {request.scope}
Return JSON with items: [{{description, quantity, unit_price}}], notes."""
    result = await generate_verified_json(prompt, "You are an invoicing assistant.", f"invoice-ai-{uuid.uuid4()}")
    return {"draft": result}


# ===========================
# Separate Admin App Endpoints
# ===========================


@router.get("/admin-app/overview")
async def admin_app_overview(req: Request):
    await require_admin(req)
    total_users = await db.users.count_documents({})
    total_jobs = await db.job_posts.count_documents({})
    total_applications = await db.job_applications.count_documents({})
    total_payments = await db.mobile_money_payments.count_documents({})
    total_invoices = await db.invoices.count_documents({})
    total_dramas = await db.drama_videos.count_documents({})
    total_songs = await db.music_songs.count_documents({})
    return {
        "users": total_users,
        "jobs": total_jobs,
        "applications": total_applications,
        "payments": total_payments,
        "invoices": total_invoices,
        "dramas": total_dramas,
        "songs": total_songs,
    }


@router.get("/admin-app/users")
async def admin_app_users(req: Request):
    await require_admin(req)
    users = await db.users.find({}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    return {"users": users}


@router.get("/admin-app/jobs")
async def admin_app_jobs(req: Request):
    await require_admin(req)
    jobs = await db.job_posts.find({}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    return {"jobs": jobs}


@router.get("/admin-app/payments")
async def admin_app_payments(req: Request):
    await require_admin(req)
    payments = await db.mobile_money_payments.find({}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    revenue = sum(p.get("amount", 0) for p in payments)
    return {"payments": payments, "total_revenue": revenue}


@router.get("/admin-app/subscriptions")
async def admin_app_subscriptions(req: Request):
    await require_admin(req)
    subs = await db.mobile_money_subscriptions.find({}, {"_id": 0}).sort("started_at", -1).limit(300).to_list(300)
    return {"subscriptions": subs}


@router.get("/admin-app/content")
async def admin_app_content(req: Request):
    await require_admin(req)
    dramas = await db.drama_videos.find({}, {"_id": 0}).limit(100).to_list(100)
    songs = await db.music_songs.find({}, {"_id": 0}).limit(100).to_list(100)
    return {"dramas": dramas, "songs": songs}


@router.get("/admin-app/analytics")
async def admin_app_analytics(req: Request):
    await require_admin(req)
    payments = await db.mobile_money_payments.find({}, {"_id": 0}).to_list(500)
    applications = await db.job_applications.find({}, {"_id": 0}).to_list(500)

    total_users = await db.users.count_documents({})
    active_subs = await db.users.count_documents(
        {"subscription_status": "active", "subscription_plan": {"$ne": "free"}}
    )
    canceled_subs = await db.users.count_documents({"subscription_status": "cancelled"})
    free_users = await db.users.count_documents(
        {"$or": [{"subscription_plan": "free"}, {"subscription_plan": {"$exists": False}}]}
    )
    basic_subs = await db.users.count_documents(
        {"subscription_plan": "basic", "subscription_status": {"$ne": "cancelled"}}
    )
    premium_subs = await db.users.count_documents(
        {"subscription_plan": "premium", "subscription_status": {"$ne": "cancelled"}}
    )

    total_revenue = sum(p.get("amount", 0) for p in payments)

    return {
        "total_users": total_users,
        "active_subscribers": active_subs,
        "canceled_subscribers": canceled_subs,
        "free_users": free_users,
        "basic_subscribers": basic_subs,
        "premium_subscribers": premium_subs,
        "total_revenue": total_revenue,
        "total_payments": len(payments),
        "avg_payment": (total_revenue / max(len(payments), 1)),
        "payment_volume": len(payments),
        "application_volume": len(applications),
    }
