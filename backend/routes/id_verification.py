"""ID Checker / AML Compliance & Enhanced Fraud Engine."""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel, validator
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import hashlib
import logging
import json
import re
import os

from fastapi.responses import FileResponse, Response, StreamingResponse
import tempfile
import asyncio

from .db import db, require_auth, require_admin, EMERGENT_LLM_KEY
from utils.llm_helper import generate_verified_json
from utils.email_templates import (
    build_idv_approved_email,
    build_idv_rejected_email,
    build_idv_pending_review_email,
    build_idv_more_info_needed_email,
)
from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
from utils.field_encryption import encrypt_field, decrypt_field, is_encrypted
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.pdf_v15_export import enforce_pdf_v15_enterprise as _base_enforce_pdf_v15_enterprise
from utils.file_security_service import enforce_file_security
from .id_verification_storage import ID_CHECKER_STORAGE_PREFIX, get_storage_object, put_storage_object
from .id_verification_access import (
    decrypt_kyc_doc,
    kyc_find_many,
    kyc_find_one,
    resolve_user_for_idv,
    revoke_idv_access_token,
)
from .id_verification_admin_reporting import (
    build_admin_dashboard_payload,
    build_admin_stats_payload,
    build_admin_super_dashboard_payload,
    manual_review_violation_query,
    render_idv_export_csv,
    render_idv_export_pdf,
)
from .id_verification_fraud import (
    ai_fraud_analysis as shared_ai_fraud_analysis,
    check_aml as shared_check_aml,
    enhanced_fraud_check as shared_enhanced_fraud_check,
)
from .id_verification_notifications import send_idv_status_email
from .id_verification_workflow import (
    ID_CHECKER_ADMIN_REVIEW,
    ID_CHECKER_AI_REVIEW,
    ID_CHECKER_APPROVED,
    ID_CHECKER_MORE_INFO_REQUIRED,
    ID_CHECKER_NOT_SUBMITTED,
    ID_CHECKER_PENDING,
    ID_CHECKER_REJECTED,
    calc_account_age,
    create_idv_notification,
    emit_state_transition,
    has_required_idv_documents,
    legacy_status_from_workflow_state,
    mask_id,
    normalize_workflow_state_in_doc,
    workflow_state_from_legacy_status,
    transition_id_checker_state,
)

router = APIRouter(prefix="")
logger = logging.getLogger(__name__)


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    try:
        return _base_enforce_pdf_v15_enterprise(payload, context)
    except Exception:
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")

# PII fields in afrikpay_kyc that require field-level encryption
_KYC_PII_FIELDS = ("full_name", "date_of_birth", "address")


RETRY_COOLDOWN_DAYS = 14
SUPPORT_REVIEW_WINDOW_DAYS = 7
MAX_SUBMISSIONS_PER_DAY = 3
MAX_DOCUMENT_DATA_SIZE = 5 * 1024 * 1024  # 5MB max
REQUIRED_IDV_DOCUMENT_TYPES = {"id_front", "id_back", "selfie"}

ID_CHECKER_PLAN_SLA_HOURS = {
    "free": 72,
    "basic": 24,
    "premium": 6,
    "admin": 4,
}

# AI verification confidence thresholds
AI_AUTO_APPROVE_THRESHOLD = 0.85
AI_AUTO_REJECT_THRESHOLD = 0.30
AI_REVIEW_FLAG_THRESHOLD = 0.60


def _normalize_plan_key(raw_plan: Optional[str], *, is_admin: bool = False) -> str:
    if is_admin:
        return "admin"
    plan = str(raw_plan or "free").strip().lower()
    if plan in {"plus", "pro"}:
        return "basic"
    if plan in {"enterprise"}:
        return "premium"
    if plan in {"free", "basic", "premium"}:
        return plan
    return "free"


def _service_lane_label(plan: str) -> str:
    if plan in {"premium", "admin"}:
        return "fast_lane"
    if plan == "basic":
        return "priority_lane"
    return "standard_lane"


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _compute_sla_meta(submitted_at: Optional[str], plan: str) -> dict:
    submitted_dt = _parse_iso_datetime(submitted_at)
    if not submitted_dt:
        return {
            "sla_due_at": None,
            "sla_breached": False,
            "sla_hours_remaining": None,
            "expected_sla_hours": ID_CHECKER_PLAN_SLA_HOURS.get(plan, ID_CHECKER_PLAN_SLA_HOURS["free"]),
        }

    due_hours = ID_CHECKER_PLAN_SLA_HOURS.get(plan, ID_CHECKER_PLAN_SLA_HOURS["free"])
    due_at = submitted_dt + timedelta(hours=due_hours)
    now_dt = datetime.now(timezone.utc)
    remaining_hours = round((due_at - now_dt).total_seconds() / 3600, 2)

    return {
        "sla_due_at": due_at.isoformat(),
        "sla_breached": now_dt > due_at,
        "sla_hours_remaining": remaining_hours,
        "expected_sla_hours": due_hours,
    }


def _workflow_progress_snapshot(workflow_state: Optional[str], documents: list) -> dict:
    ordered_states = [
        ID_CHECKER_NOT_SUBMITTED,
        ID_CHECKER_PENDING,
        ID_CHECKER_AI_REVIEW,
        ID_CHECKER_ADMIN_REVIEW,
        ID_CHECKER_APPROVED,
        ID_CHECKER_REJECTED,
        ID_CHECKER_MORE_INFO_REQUIRED,
    ]
    current_state = str(workflow_state or ID_CHECKER_NOT_SUBMITTED).upper()
    try:
        state_index = ordered_states.index(current_state)
    except ValueError:
        state_index = 0

    uploaded_types = {
        str((doc or {}).get("type") or "").lower()
        for doc in (documents or [])
        if isinstance(doc, dict)
    }
    uploaded_types = {t for t in uploaded_types if t}
    required = sorted(REQUIRED_IDV_DOCUMENT_TYPES)
    missing = sorted(list(REQUIRED_IDV_DOCUMENT_TYPES - uploaded_types))

    return {
        "state_index": state_index,
        "total_states": len(ordered_states),
        "state_progress_pct": round(((state_index + 1) / len(ordered_states)) * 100, 1),
        "required_documents": required,
        "uploaded_documents": sorted(uploaded_types),
        "missing_documents": missing,
        "documents_complete": len(missing) == 0,
        "document_progress_pct": round((len(uploaded_types.intersection(REQUIRED_IDV_DOCUMENT_TYPES)) / len(REQUIRED_IDV_DOCUMENT_TYPES)) * 100, 1),
    }


async def _build_id_checker_operations_kpis(lookback_days: int = 30) -> dict:
    lookback = max(1, min(int(lookback_days or 30), 180))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=lookback)).isoformat()

    records = await _kyc_find_many(
        {"submitted_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "user_id": 1,
            "submitted_at": 1,
            "status": 1,
            "workflow_state": 1,
            "documents": 1,
        },
        sort=("submitted_at", -1),
        limit=5000,
    )

    user_ids = [str(r.get("user_id") or "") for r in records if r.get("user_id")]
    user_docs = []
    if user_ids:
        user_docs = await db.users.find(
            {"user_id": {"$in": list(set(user_ids))}},
            {"_id": 0, "user_id": 1, "subscription_plan": 1, "is_admin": 1},
        ).to_list(len(set(user_ids)) + 20)
    plan_map = {
        str(u.get("user_id")): _normalize_plan_key(
            str(u.get("subscription_plan") or "free"),
            is_admin=bool(u.get("is_admin", False)),
        )
        for u in user_docs
    }

    total = len(records)
    state_counts = {
        ID_CHECKER_NOT_SUBMITTED: 0,
        ID_CHECKER_PENDING: 0,
        ID_CHECKER_AI_REVIEW: 0,
        ID_CHECKER_ADMIN_REVIEW: 0,
        ID_CHECKER_APPROVED: 0,
        ID_CHECKER_REJECTED: 0,
        ID_CHECKER_MORE_INFO_REQUIRED: 0,
    }
    completed_docs = 0
    missing_docs = 0
    sla_breaches = 0
    lane_counts = {"standard_lane": 0, "priority_lane": 0, "fast_lane": 0}

    for row in records:
        workflow_state = str(
            row.get("workflow_state")
            or _workflow_state_from_legacy_status(row.get("status"))
            or ID_CHECKER_NOT_SUBMITTED
        ).upper()
        if workflow_state not in state_counts:
            state_counts[workflow_state] = 0
        state_counts[workflow_state] += 1

        plan = plan_map.get(str(row.get("user_id") or ""), "free")
        lane = _service_lane_label(plan)
        lane_counts[lane] = lane_counts.get(lane, 0) + 1

        progress = _workflow_progress_snapshot(workflow_state, row.get("documents") or [])
        if progress["documents_complete"]:
            completed_docs += 1
        else:
            missing_docs += 1

        sla_meta = _compute_sla_meta(row.get("submitted_at"), plan)
        active_states = {ID_CHECKER_PENDING, ID_CHECKER_AI_REVIEW, ID_CHECKER_ADMIN_REVIEW, ID_CHECKER_MORE_INFO_REQUIRED}
        if workflow_state in active_states and bool(sla_meta.get("sla_breached")):
            sla_breaches += 1

    approved = state_counts.get(ID_CHECKER_APPROVED, 0)
    rejected = state_counts.get(ID_CHECKER_REJECTED, 0)
    pending = (
        state_counts.get(ID_CHECKER_PENDING, 0)
        + state_counts.get(ID_CHECKER_AI_REVIEW, 0)
        + state_counts.get(ID_CHECKER_ADMIN_REVIEW, 0)
        + state_counts.get(ID_CHECKER_MORE_INFO_REQUIRED, 0)
    )

    return {
        "lookback_days": lookback,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": total,
        "approval_rate_pct": round((approved / total) * 100, 2) if total else 0,
        "rejection_rate_pct": round((rejected / total) * 100, 2) if total else 0,
        "pending_rate_pct": round((pending / total) * 100, 2) if total else 0,
        "document_completion_rate_pct": round((completed_docs / total) * 100, 2) if total else 0,
        "sla_breach_cases": sla_breaches,
        "state_counts": state_counts,
        "service_lane_counts": lane_counts,
        "docs_missing_cases": missing_docs,
    }


async def _build_id_checker_conversion_funnel(lookback_days: int = 30) -> dict:
    lookback = max(1, min(int(lookback_days or 30), 180))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=lookback)).isoformat()

    records = await _kyc_find_many(
        {"submitted_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "user_id": 1,
            "submitted_at": 1,
            "status": 1,
            "workflow_state": 1,
            "documents": 1,
            "ai_verification": 1,
        },
        sort=("submitted_at", -1),
        limit=5000,
    )

    stage_submitted = len(records)
    stage_docs_complete = 0
    stage_ai_reviewed = 0
    stage_admin_review = 0
    stage_approved = 0

    for row in records:
        workflow_state = str(
            row.get("workflow_state")
            or _workflow_state_from_legacy_status(row.get("status"))
            or ID_CHECKER_NOT_SUBMITTED
        ).upper()
        docs = row.get("documents") or []
        progress = _workflow_progress_snapshot(workflow_state, docs)
        ai = row.get("ai_verification") or {}

        if progress.get("documents_complete"):
            stage_docs_complete += 1
        if ai.get("confidence_score") is not None or workflow_state in {ID_CHECKER_AI_REVIEW, ID_CHECKER_ADMIN_REVIEW, ID_CHECKER_APPROVED, ID_CHECKER_REJECTED, ID_CHECKER_MORE_INFO_REQUIRED}:
            stage_ai_reviewed += 1
        if workflow_state in {ID_CHECKER_ADMIN_REVIEW, ID_CHECKER_APPROVED, ID_CHECKER_REJECTED, ID_CHECKER_MORE_INFO_REQUIRED}:
            stage_admin_review += 1
        if workflow_state == ID_CHECKER_APPROVED:
            stage_approved += 1

    def pct(part: int, whole: int) -> float:
        return round((part / whole) * 100, 2) if whole else 0.0

    conversion = {
        "submitted_to_docs_complete": pct(stage_docs_complete, stage_submitted),
        "docs_complete_to_ai_reviewed": pct(stage_ai_reviewed, stage_docs_complete),
        "ai_reviewed_to_admin_review": pct(stage_admin_review, stage_ai_reviewed),
        "admin_review_to_approved": pct(stage_approved, stage_admin_review),
        "submitted_to_approved": pct(stage_approved, stage_submitted),
    }

    insights = []
    missing_docs = max(stage_submitted - stage_docs_complete, 0)
    if stage_submitted > 0 and missing_docs / stage_submitted >= 0.25:
        insights.append("Document completion is a major drop-off point. Improve user capture guidance and reminder nudges.")
    if stage_admin_review > 0 and stage_approved / max(stage_admin_review, 1) < 0.5:
        insights.append("Approval ratio after admin review is below target. Revisit reject reasons and policy calibration.")
    if not insights:
        insights.append("Funnel is stable. Continue monitoring lane-SLA and document-quality trends.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback,
        "funnel": {
            "submitted": stage_submitted,
            "docs_complete": stage_docs_complete,
            "ai_reviewed": stage_ai_reviewed,
            "admin_reviewed": stage_admin_review,
            "approved": stage_approved,
        },
        "conversion_rates_pct": conversion,
        "dropoff": {
            "submitted_to_docs_complete": max(stage_submitted - stage_docs_complete, 0),
            "docs_complete_to_ai_reviewed": max(stage_docs_complete - stage_ai_reviewed, 0),
            "ai_reviewed_to_admin_review": max(stage_ai_reviewed - stage_admin_review, 0),
            "admin_review_to_approved": max(stage_admin_review - stage_approved, 0),
        },
        "insights": insights,
    }


async def _build_id_checker_experience_summary(request: Request) -> dict:
    user = await _resolve_user_for_idv(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "subscription_plan": 1, "is_admin": 1},
    )
    plan = _normalize_plan_key(
        str((user_doc or {}).get("subscription_plan") or "free"),
        is_admin=bool((user_doc or {}).get("is_admin", False)),
    )
    workflow_state = str((kyc or {}).get("workflow_state") or ID_CHECKER_NOT_SUBMITTED).upper()
    progress = _workflow_progress_snapshot(workflow_state, (kyc or {}).get("documents") or [])
    sla_meta = _compute_sla_meta((kyc or {}).get("submitted_at"), plan)

    nudges = []
    if not progress.get("documents_complete"):
        nudges.append("Complete all 3 required captures to unlock accelerated review.")
    if workflow_state in {ID_CHECKER_PENDING, ID_CHECKER_AI_REVIEW, ID_CHECKER_ADMIN_REVIEW, ID_CHECKER_MORE_INFO_REQUIRED}:
        nudges.append("Stay available for follow-up requests to reduce turnaround time.")
    if workflow_state == ID_CHECKER_APPROVED:
        nudges.append("Your verification is approved. Keep profile information updated to preserve trust score.")

    trust_score = 30
    if progress.get("documents_complete"):
        trust_score += 30
    if workflow_state in {ID_CHECKER_AI_REVIEW, ID_CHECKER_ADMIN_REVIEW, ID_CHECKER_MORE_INFO_REQUIRED}:
        trust_score += 20
    if workflow_state == ID_CHECKER_APPROVED:
        trust_score = 100

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan,
        "service_lane": _service_lane_label(plan),
        "workflow_state": workflow_state,
        "progress": progress,
        "sla": sla_meta,
        "trust_readiness_score": trust_score,
        "nudges": nudges,
    }


async def _build_id_checker_transition_summary(user_id: str, workflow_state: str, sla_meta: dict) -> dict:
    transition_docs = await db.id_checker_state_transitions.find(
        {"user_id": user_id},
        {"_id": 0, "from_state": 1, "to_state": 1, "actor": 1, "reason": 1, "metadata": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(6)

    active_state = str(workflow_state or ID_CHECKER_NOT_SUBMITTED).upper()
    milestone_order = [
        ID_CHECKER_NOT_SUBMITTED,
        ID_CHECKER_PENDING,
        ID_CHECKER_AI_REVIEW,
        ID_CHECKER_ADMIN_REVIEW,
        ID_CHECKER_APPROVED,
        ID_CHECKER_REJECTED,
        ID_CHECKER_MORE_INFO_REQUIRED,
    ]
    handoff_map = {
        ID_CHECKER_PENDING: "submission-intake",
        ID_CHECKER_AI_REVIEW: "ai-review",
        ID_CHECKER_ADMIN_REVIEW: "human-review",
        ID_CHECKER_MORE_INFO_REQUIRED: "follow-up",
        ID_CHECKER_APPROVED: "completed",
        ID_CHECKER_REJECTED: "completed",
    }
    eta_label_map = {
        ID_CHECKER_NOT_SUBMITTED: "Awaiting secure submission",
        ID_CHECKER_PENDING: "Queued for intake validation",
        ID_CHECKER_AI_REVIEW: "AI document triage in progress",
        ID_CHECKER_ADMIN_REVIEW: "Manual reviewer handoff in progress",
        ID_CHECKER_MORE_INFO_REQUIRED: "Waiting for customer follow-up",
        ID_CHECKER_APPROVED: "Verification completed",
        ID_CHECKER_REJECTED: "Decision completed",
    }
    owner_label_map = {
        ID_CHECKER_NOT_SUBMITTED: "You",
        ID_CHECKER_PENDING: "Intake queue",
        ID_CHECKER_AI_REVIEW: "AI review engine",
        ID_CHECKER_ADMIN_REVIEW: "Trust & Safety reviewer",
        ID_CHECKER_MORE_INFO_REQUIRED: "Customer action required",
        ID_CHECKER_APPROVED: "Trust & Safety reviewer",
        ID_CHECKER_REJECTED: "Trust & Safety reviewer",
    }

    progress_index = milestone_order.index(active_state) if active_state in milestone_order else 0
    recent_events = []
    for idx, event in enumerate(transition_docs):
        to_state = str(event.get("to_state") or "").upper()
        recent_events.append(
            {
                "event_id": f"timeline-{idx}",
                "to_state": to_state,
                "from_state": str(event.get("from_state") or "").upper(),
                "label": to_state.replace("_", " ").title() if to_state else "State updated",
                "actor": str(event.get("actor") or "system").replace("_", " ").title(),
                "reason": str(event.get("reason") or "State updated").replace("_", " "),
                "created_at": event.get("created_at"),
            }
        )

    milestones = []
    for idx, state in enumerate(milestone_order):
        status = "upcoming"
        if state == active_state:
            status = "current"
        elif idx < progress_index:
            status = "completed"
        elif active_state in {ID_CHECKER_APPROVED, ID_CHECKER_REJECTED} and state in {ID_CHECKER_APPROVED, ID_CHECKER_REJECTED}:
            status = "completed" if state == active_state else "skipped"
        elif active_state == ID_CHECKER_MORE_INFO_REQUIRED and state == ID_CHECKER_APPROVED:
            status = "blocked"

        milestones.append(
            {
                "state": state,
                "label": state.replace("_", " ").title(),
                "status": status,
                "owner": owner_label_map.get(state, "Trust workflow"),
                "eta_label": eta_label_map.get(state, "In progress"),
            }
        )

    return {
        "current_handoff": handoff_map.get(active_state, "submission-intake"),
        "eta_message": eta_label_map.get(active_state, "Verification workflow in progress"),
        "owner_label": owner_label_map.get(active_state, "Trust workflow"),
        "sla_due_at": sla_meta.get("sla_due_at"),
        "sla_hours_remaining": sla_meta.get("sla_hours_remaining"),
        "recent_events": recent_events,
        "milestones": milestones,
    }

_workflow_state_from_legacy_status = workflow_state_from_legacy_status
_legacy_status_from_workflow_state = legacy_status_from_workflow_state
_normalize_workflow_state_in_doc = normalize_workflow_state_in_doc
_emit_state_transition = emit_state_transition
_transition_id_checker_state = transition_id_checker_state
_has_required_idv_documents = has_required_idv_documents
_create_idv_notification = create_idv_notification
_mask_id = mask_id
_calc_account_age = calc_account_age
_put_storage_object = put_storage_object
_get_storage_object = get_storage_object
_resolve_user_for_idv = resolve_user_for_idv
_revoke_idv_access_token = revoke_idv_access_token
check_aml = shared_check_aml
enhanced_fraud_check = shared_enhanced_fraud_check


def _decrypt_kyc_doc(doc):
    return decrypt_kyc_doc(
        doc,
        pii_fields=_KYC_PII_FIELDS,
        decrypt_field=decrypt_field,
        is_encrypted=is_encrypted,
        normalize_workflow_state_in_doc=normalize_workflow_state_in_doc,
    )


async def _kyc_find_one(filter_, projection=None):
    return await kyc_find_one(
        filter_,
        projection=projection,
        pii_fields=_KYC_PII_FIELDS,
        decrypt_field=decrypt_field,
        encrypt_field=encrypt_field,
        is_encrypted=is_encrypted,
        normalize_workflow_state_in_doc=normalize_workflow_state_in_doc,
        logger=logger,
    )


async def _kyc_find_many(filter_, projection=None, sort=None, limit=1000):
    return await kyc_find_many(
        filter_,
        projection=projection,
        sort=sort,
        limit=limit,
        pii_fields=_KYC_PII_FIELDS,
        decrypt_field=decrypt_field,
        is_encrypted=is_encrypted,
        normalize_workflow_state_in_doc=normalize_workflow_state_in_doc,
    )


async def _send_idv_status_email(user_id, status, ai_result, kyc):
    return await send_idv_status_email(
        user_id=user_id,
        status=status,
        ai_result=ai_result,
        kyc=kyc,
        logger=logger,
        build_idv_approved_email=build_idv_approved_email,
        build_idv_rejected_email=build_idv_rejected_email,
        build_idv_pending_review_email=build_idv_pending_review_email,
        build_idv_more_info_needed_email=build_idv_more_info_needed_email,
    )


async def ai_fraud_analysis(user_id, tx_data):
    return await shared_ai_fraud_analysis(user_id, tx_data, kyc_lookup=_kyc_find_one, logger=logger)


_manual_review_violation_query = manual_review_violation_query


# ── AI-Powered ID Checker ──


async def ai_verify_kyc_submission(kyc_data: dict, user_id: str) -> dict:
    """Run AI-powered verification analysis on a KYC submission.
    Checks data consistency, fraud patterns, and provides confidence scoring."""
    try:
        # Gather user behavioral context
        user = await db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "created_at": 1, "email": 1, "subscription_plan": 1}
        )
        past_submissions = await db.id_verification_submissions_log.count_documents({"user_id": user_id})
        past_rejections = await db.afrikpay_kyc.count_documents({"user_id": user_id, "status": "rejected"})
        await db.login_sessions.count_documents(
            {"user_id": user_id}
        ) if "login_sessions" in await db.list_collection_names() else 0

        # Check for duplicate ID number hash across users
        id_hash = kyc_data.get("id_number_hash", "")
        duplicate_id = (
            await db.afrikpay_kyc.count_documents(
                {
                    "id_number_hash": id_hash,
                    "user_id": {"$ne": user_id},
                    "status": {"$in": ["verified", "pending_review"]},
                }
            )
            if id_hash
            else 0
        )

        # Build context for AI analysis
        context = {
            "full_name": kyc_data.get("full_name", ""),
            "date_of_birth": kyc_data.get("date_of_birth", ""),
            "nationality": kyc_data.get("nationality", ""),
            "id_type": kyc_data.get("id_type", ""),
            "address": kyc_data.get("address", ""),
            "phone": kyc_data.get("phone", ""),
            "level": kyc_data.get("level", 1),
            "documents_count": len(kyc_data.get("documents", [])),
            "has_id_front": any(d.get("type") == "id_front" for d in kyc_data.get("documents", [])),
            "has_id_back": any(d.get("type") == "id_back" for d in kyc_data.get("documents", [])),
            "has_selfie": any(d.get("type") == "selfie" for d in kyc_data.get("documents", [])),
            "past_submission_attempts": past_submissions,
            "past_rejections": past_rejections,
            "duplicate_id_detected": duplicate_id > 0,
            "account_age_days": _calc_account_age(user),
        }

        system_msg = """You are an expert ID Checker analyst for a fintech platform operating in Africa.
Analyze the submitted ID Checker data for authenticity, consistency, and fraud risk.
Consider: name-nationality consistency, phone format matching country, age appropriateness,
address format, document completeness, submission patterns, and behavioral signals."""

        prompt = f"""Analyze this ID Checker submission and return a JSON assessment.

Submission Data:
- Name: {context["full_name"]}
- DOB: {context["date_of_birth"]}
- Nationality: {context["nationality"]}
- ID Type: {context["id_type"]}
- Address: {context["address"]}
- Phone: {context["phone"]}
- Verification Level: {context["level"]}

Document Status:
- ID Front: {"Uploaded" if context["has_id_front"] else "Missing"}
- ID Back: {"Uploaded" if context["has_id_back"] else "Missing"}
- Selfie: {"Uploaded" if context["has_selfie"] else "Missing"}
- Total Documents: {context["documents_count"]}

Behavioral Context:
- Past submission attempts: {context["past_submission_attempts"]}
- Past rejections: {context["past_rejections"]}
- Duplicate ID detected (same ID used by another user): {context["duplicate_id_detected"]}
- Account age: {context["account_age_days"]} days

Return ONLY valid JSON:
{{
  "confidence_score": 0.0-1.0,
  "risk_level": "low|medium|high|critical",
  "recommendation": "auto_approve|manual_review|auto_reject",
  "checks": [
    {{"check": "name_nationality_consistency", "passed": true/false, "detail": "..."}},
    {{"check": "phone_format_validation", "passed": true/false, "detail": "..."}},
    {{"check": "age_verification", "passed": true/false, "detail": "..."}},
    {{"check": "address_quality", "passed": true/false, "detail": "..."}},
    {{"check": "document_completeness", "passed": true/false, "detail": "..."}},
    {{"check": "duplicate_identity", "passed": true/false, "detail": "..."}},
    {{"check": "behavioral_analysis", "passed": true/false, "detail": "..."}}
  ],
  "flags": ["list of concerns if any"],
  "summary": "Brief overall assessment"
}}"""

        result = await generate_verified_json(prompt, system_msg, f"idv_{user_id[:8]}")
        if result:
            result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            result["analyzer"] = "gpt-4o"
            return result

    except Exception as e:
        logger.warning(f"AI ID Checker analysis error for {user_id}: {e}")

    # Fallback if AI is unavailable
    return {
        "confidence_score": 0.5,
        "risk_level": "medium",
        "recommendation": "manual_review",
        "checks": [],
        "flags": ["AI analysis unavailable - defaulting to manual review"],
        "summary": "AI analysis could not be completed. Manual review required.",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "analyzer": "fallback",
    }


async def trigger_risk_based_id_verification(user_id: str, risk_payload: dict, triggered_by: str = "risk_engine") -> dict:
    """Automatically require ID Checker when the progressive risk engine reaches CRITICAL."""
    now_iso = datetime.now(timezone.utc).isoformat()

    user = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "phone": 1},
    )
    if not user:
        return {"triggered": False, "reason": "user_not_found"}

    existing = await _kyc_find_one({"user_id": user_id}, {"_id": 0})
    risk_snapshot = {
        "engine_status": risk_payload.get("risk_engine_status", "ACTIVE"),
        "risk_score": int(risk_payload.get("risk_score") or 0),
        "risk_level": str(risk_payload.get("risk_level") or "critical").lower(),
        "trigger": risk_payload.get("trigger", "SESSION_LOCK_AND_ID_VERIFICATION"),
        "session_protection": risk_payload.get("session_protection", "SESSION_LOCKDOWN"),
        "false_positive_rate_pct": float(risk_payload.get("false_positive_rate_pct") or 0),
        "confidence": float(risk_payload.get("confidence") or 0),
        "output_block": risk_payload.get("output_block", ""),
        "triggered_by": triggered_by,
        "triggered_at": now_iso,
    }

    if existing:
        current_state = str(existing.get("workflow_state") or _workflow_state_from_legacy_status(existing.get("status"))).upper()
        transition = await _transition_id_checker_state(
            user_id=user_id,
            current_state=current_state,
            target_state=ID_CHECKER_PENDING,
            actor=f"system:{triggered_by}",
            reason="risk_engine_forced_reverification",
            metadata={"risk_score": risk_snapshot["risk_score"], "risk_level": risk_snapshot["risk_level"]},
        )
        update_doc = {
            "status": transition["status"],
            "workflow_state": transition["workflow_state"],
            "tier": "pending",
            "level": max(int(existing.get("level") or 1), 2),
            "risk_trigger": risk_snapshot,
            "verification_required_by_engine": True,
            "risk_verification_required_at": now_iso,
        }
        await db.afrikpay_kyc.update_one({"user_id": user_id}, {"$set": update_doc})
    else:
        seed_id_hash = hashlib.sha256(f"risk-trigger-{user_id}".encode()).hexdigest()
        kyc_doc = {
            "kyc_id": f"idv_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "full_name": encrypt_field(user.get("name") or "Risk Verification Required"),
            "date_of_birth": encrypt_field("1900-01-01"),
            "nationality": "UNK",
            "id_type": "national_id",
            "id_number_hash": seed_id_hash,
            "address": encrypt_field("Pending secure re-verification"),
            "phone": user.get("phone") or "",
            "level": 2,
            "status": "pending_review",
            "workflow_state": ID_CHECKER_PENDING,
            "tier": "pending",
            "documents": [],
            "submitted_at": now_iso,
            "verification_required_by_engine": True,
            "risk_verification_required_at": now_iso,
            "risk_trigger": risk_snapshot,
            "auto_verification": {
                "status": "pending_review",
                "score": max(0, 100 - int(risk_payload.get("risk_score") or 0)),
                "issues": ["Progressive Risk Engine critical trigger"],
                "needs_review": True,
            },
        }
        await db.afrikpay_kyc.insert_one(kyc_doc)
        await _emit_state_transition(
            user_id=user_id,
            from_state=ID_CHECKER_NOT_SUBMITTED,
            to_state=ID_CHECKER_PENDING,
            actor=f"system:{triggered_by}",
            reason="risk_engine_submission_seeded",
            metadata={"risk_score": risk_snapshot["risk_score"], "risk_level": risk_snapshot["risk_level"]},
        )

    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "kyc_required_due_to_risk": True,
                "risk_verification_required_at": now_iso,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    await db.notifications.insert_one(
        {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": "idv_risk_triggered",
            "title": "ID Checker required",
            "body": "We detected elevated risk on your account. Complete ID Checker to restore privileged access.",
            "read": False,
            "created_at": now_iso,
            "metadata": {
                "risk_score": risk_snapshot["risk_score"],
                "risk_level": risk_snapshot["risk_level"],
                "trigger": risk_snapshot["trigger"],
            },
        }
    )

    try:
        await _send_idv_status_email(
            user_id,
            "pending_review",
            {
                "confidence_score": float(risk_payload.get("confidence") or 0),
                "flags": [
                    f"Progressive Risk Engine trigger: score {risk_snapshot['risk_score']} ({risk_snapshot['risk_level']})",
                    f"Session protection: {risk_snapshot['session_protection']}",
                ],
            },
            await _kyc_find_one({"user_id": user_id}, {"_id": 0}) or {},
        )
    except Exception as email_exc:
        logger.warning(f"Risk-triggered IDV email skipped for {user_id}: {email_exc}")

    return {
        "triggered": True,
        "user_id": user_id,
        "risk_level": risk_snapshot["risk_level"],
        "risk_score": risk_snapshot["risk_score"],
        "status": "pending_review",
        "workflow_state": ID_CHECKER_PENDING,
        "triggered_at": now_iso,
    }


async def _run_ai_verification_pipeline(user_id: str) -> dict:
    """Full AI verification pipeline: combines rule-based + AI text analysis + AI vision analysis."""
    kyc = await _kyc_find_one({"user_id": user_id}, {"_id": 0})
    if not kyc:
        return {"error": "No KYC record found"}

    # Run text-based AI analysis
    ai_result = await ai_verify_kyc_submission(kyc, user_id)
    confidence = ai_result.get("confidence_score", 0.5)
    recommendation = ai_result.get("recommendation", "manual_review")

    # Run vision analysis on actual document images
    vision_result = None
    has_files = any(d.get("filename") for d in kyc.get("documents", []))
    if has_files:
        try:
            vision_result = await _run_vision_verification(user_id, kyc)
            vision_conf = vision_result.get("vision_confidence", 0.5)
            # Merge vision findings into confidence
            confidence = round((confidence * 0.5) + (vision_conf * 0.5), 3)
            # If vision detects tampering or photo-of-photo, downgrade
            if vision_result.get("tampering_detected"):
                confidence = min(confidence, 0.25)
                recommendation = "auto_reject"
                ai_result["flags"] = ai_result.get("flags", []) + ["Document tampering detected by AI vision"]
            if vision_result.get("photo_of_photo_detected"):
                confidence = min(confidence, 0.30)
                recommendation = "auto_reject"
                ai_result["flags"] = ai_result.get("flags", []) + ["Selfie appears to be a photo of a photo"]
            # If name/DOB don't match document
            if vision_result.get("name_match") is False:
                confidence = min(confidence, 0.40)
                ai_result["flags"] = ai_result.get("flags", []) + ["Name on document doesn't match submitted name"]
            if vision_result.get("dob_match") is False:
                confidence = min(confidence, 0.45)
                ai_result["flags"] = ai_result.get("flags", []) + ["DOB on document doesn't match submitted DOB"]
            ai_result["confidence_score"] = confidence
            ai_result["recommendation"] = recommendation
            ai_result["vision_analysis"] = vision_result
        except Exception as e:
            logger.warning(f"Vision analysis failed in pipeline for {user_id}: {e}")

    # Combine with existing rule-based score
    rule_score = kyc.get("auto_verification", {}).get("score", 50)
    combined_score = round((rule_score / 100 * 0.4) + (confidence * 0.6), 3)

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "ai_verification": ai_result,
        "combined_score": combined_score,
        "ai_verified_at": now_iso,
    }

    # POLICY LOCK: AI can score and recommend only.
    # Final decisions (approved/rejected) must come from admin manual review.
    current_workflow_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()
    final_states = {ID_CHECKER_APPROVED, ID_CHECKER_REJECTED}

    proposed_decision = "manual_review"
    if recommendation == "auto_approve" and confidence >= AI_AUTO_APPROVE_THRESHOLD and rule_score >= 80:
        proposed_decision = "proposed_approve"
    elif recommendation == "auto_reject" or confidence <= AI_AUTO_REJECT_THRESHOLD:
        proposed_decision = "proposed_reject"

    ai_result["proposed_decision"] = proposed_decision
    ai_result["manual_review_required"] = True

    if current_workflow_state in final_states:
        update["verification_method"] = "ai_scored_final_status_locked"
    else:
        state_patch = {"workflow_state": current_workflow_state, "status": _legacy_status_from_workflow_state(current_workflow_state)}
        if current_workflow_state in {ID_CHECKER_PENDING, ID_CHECKER_MORE_INFO_REQUIRED}:
            state_patch = await _transition_id_checker_state(
                user_id=user_id,
                current_state=current_workflow_state,
                target_state=ID_CHECKER_AI_REVIEW,
                actor="ai_pipeline",
                reason="ai_precheck_started",
            )
            state_patch = await _transition_id_checker_state(
                user_id=user_id,
                current_state=state_patch["workflow_state"],
                target_state=ID_CHECKER_ADMIN_REVIEW,
                actor="ai_pipeline",
                reason="ai_precheck_completed",
                metadata={
                    "confidence": confidence,
                    "combined_score": combined_score,
                    "proposed_decision": proposed_decision,
                },
            )
        elif current_workflow_state == ID_CHECKER_AI_REVIEW:
            state_patch = await _transition_id_checker_state(
                user_id=user_id,
                current_state=current_workflow_state,
                target_state=ID_CHECKER_ADMIN_REVIEW,
                actor="ai_pipeline",
                reason="ai_precheck_completed",
                metadata={
                    "confidence": confidence,
                    "combined_score": combined_score,
                    "proposed_decision": proposed_decision,
                },
            )

        update["workflow_state"] = state_patch["workflow_state"]
        update["status"] = state_patch["status"]
        update["tier"] = "pending"
        update["verification_method"] = "ai_scored_pending_admin_review"

    await db.afrikpay_kyc.update_one({"user_id": user_id}, {"$set": update})

    # Notify user that AI scoring completed but admin decision is required.
    if current_workflow_state not in final_states:
        await _create_idv_notification(
            user_id=user_id,
            notif_type="id_checker_admin_review",
            title="ID Checker Under Admin Review",
            message="AI pre-check is complete. Your ID Checker case now requires admin manual review.",
            metadata={
                "proposed_decision": proposed_decision,
                "confidence": confidence,
                "combined_score": combined_score,
            },
            now_iso=now_iso,
        )
        await _send_idv_status_email(user_id, "pending_review", ai_result, {**kyc, **update})

    return {
        "status": (update.get("status") or _legacy_status_from_workflow_state(current_workflow_state)),
        "workflow_state": update.get("workflow_state", current_workflow_state),
        "ai_analysis": ai_result,
        "combined_score": combined_score,
        "decision": update.get("verification_method", "unknown"),
    }


# ── AI Vision Document Analysis ──

MEDIA_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "idv")



async def ai_vision_analyze_document(user_id: str, doc_type: str, filepath: str, kyc_data: dict) -> dict:
    """Use GPT-4o vision to OCR/analyze an ID document image."""
    try:
        if not os.path.exists(filepath):
            return {"error": "File not found", "doc_type": doc_type}

        ext = filepath.rsplit(".", 1)[-1].lower()
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
        mime = mime_map.get(ext, "image/jpeg")

        image_file = FileContentWithMimeType(file_path=filepath, mime_type=mime)

        prompts = {
            "id_front": f"""Analyze this ID document front side. Extract all visible text and fields.
The holder claims: Name="{kyc_data.get("full_name", "N/A")}", DOB="{kyc_data.get("date_of_birth", "N/A")}", Nationality="{kyc_data.get("nationality", "N/A")}", ID Type="{kyc_data.get("id_type", "N/A")}".

Return ONLY valid JSON:
{{"document_type_detected": "passport|national_id|drivers_license|unknown",
"extracted_name": "name from document or null",
"extracted_dob": "DOB from document or null",
"extracted_id_number": "ID number from document or null",
"extracted_nationality": "nationality/country from document or null",
"name_match": true/false,
"dob_match": true/false,
"document_quality": "good|fair|poor|unreadable",
"is_authentic_looking": true/false,
"tampering_detected": true/false,
"confidence": 0.0-1.0,
"issues": ["list of concerns"],
"summary": "brief assessment"}}""",
            "id_back": """Analyze this ID document back side. Extract any visible text, barcodes, or MRZ zones.

Return ONLY valid JSON:
{"has_mrz": true/false,
"has_barcode": true/false,
"extracted_text": "any readable text",
"document_quality": "good|fair|poor|unreadable",
"is_authentic_looking": true/false,
"tampering_detected": true/false,
"confidence": 0.0-1.0,
"issues": ["list of concerns"],
"summary": "brief assessment"}""",
            "selfie": """Analyze this selfie photo for ID Checker.
Check: Is this a real person (not a photo of a photo)? Is the face clear and well-lit?

Return ONLY valid JSON:
{"is_real_person": true/false,
"face_clearly_visible": true/false,
"photo_of_photo_detected": true/false,
"face_quality": "good|fair|poor",
"lighting": "good|fair|poor",
"confidence": 0.0-1.0,
"issues": ["list of concerns"],
"summary": "brief assessment"}""",
        }

        prompt = prompts.get(doc_type, prompts["id_front"])

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"idv_vision_{user_id[:8]}_{doc_type}",
            system_message="You are an expert document verification analyst. Analyze ID documents for authenticity and extract information. Return ONLY valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt, file_contents=[image_file]))
        text = response.text if hasattr(response, "text") else str(response)

        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        result = json.loads(clean)
        result["doc_type"] = doc_type
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        result["analyzer"] = "gpt-4o-vision"
        return result

    except Exception as e:
        logger.warning(f"Vision analysis failed for {user_id}/{doc_type}: {e}")
        return {
            "doc_type": doc_type,
            "error": str(e),
            "confidence": 0.3,
            "summary": "Vision analysis could not be completed",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "analyzer": "vision_fallback",
        }


async def _run_vision_verification(user_id: str, kyc: dict) -> dict:
    """Run vision analysis on all uploaded documents for a user."""
    documents = kyc.get("documents", [])
    results = {}

    for doc in documents:
        filename = doc.get("filename")
        storage_path = doc.get("storage_path")
        content_type = doc.get("content_type") or "image/jpeg"
        doc_type = doc.get("type")
        if (not filename and not storage_path) or not doc_type:
            continue

        filepath = None
        tmp_path = None
        if storage_path:
            try:
                blob, resolved_type = _get_storage_object(storage_path)
                ctype = (resolved_type or content_type or "image/jpeg").lower()
                ext = "jpg"
                if "png" in ctype:
                    ext = "png"
                elif "webp" in ctype:
                    ext = "webp"
                elif "pdf" in ctype:
                    ext = "pdf"
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                    tmp.write(blob)
                    tmp_path = tmp.name
                filepath = tmp_path
            except Exception as e:
                logger.warning("Failed to fetch ID Checker doc from storage for vision analysis: %s", e)

        if not filepath and filename:
            local_path = os.path.join(MEDIA_BASE, user_id, filename)
            if os.path.exists(local_path):
                filepath = local_path

        if filepath:
            try:
                result = await ai_vision_analyze_document(user_id, doc_type, filepath, kyc)
                results[doc_type] = result
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

    # Compute overall vision score
    total_conf = 0
    count = 0
    all_issues = []
    for dtype, res in results.items():
        if "confidence" in res:
            total_conf += res["confidence"]
            count += 1
        all_issues.extend(res.get("issues", []))

    avg_confidence = round(total_conf / max(count, 1), 3)

    # Check name/DOB match from front ID
    front = results.get("id_front", {})
    name_match = front.get("name_match", None)
    dob_match = front.get("dob_match", None)
    tampering = any(r.get("tampering_detected") for r in results.values())
    photo_of_photo = results.get("selfie", {}).get("photo_of_photo_detected", False)

    return {
        "documents_analyzed": list(results.keys()),
        "document_results": results,
        "vision_confidence": avg_confidence,
        "name_match": name_match,
        "dob_match": dob_match,
        "tampering_detected": tampering,
        "photo_of_photo_detected": photo_of_photo,
        "all_issues": all_issues,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/kyc/document-file/{doc_type}")
async def serve_document_file(doc_type: str, request: Request):
    """Serve an uploaded document image for the authenticated user."""
    user = await _resolve_user_for_idv(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No KYC record")

    doc = next((d for d in kyc.get("documents", []) if d.get("type") == doc_type), None)
    if not doc or not doc.get("filename"):
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = doc.get("storage_path")
    if storage_path:
        try:
            content, content_type = _get_storage_object(storage_path)
            return Response(content=content, media_type=doc.get("content_type") or content_type)
        except Exception as e:
            logger.warning("Storage fetch failed for %s: %s", storage_path, e)

    filepath = os.path.join(MEDIA_BASE, user.user_id, doc["filename"])
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath, media_type=doc.get("content_type", "image/jpeg"))


@router.get("/admin/document-file/{target_user_id}/{doc_type}")
async def admin_serve_document_file(target_user_id: str, doc_type: str, request: Request):
    """Admin: Serve an uploaded document image for any user."""
    await require_admin(request)
    kyc = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No KYC record")

    doc = next((d for d in kyc.get("documents", []) if d.get("type") == doc_type), None)
    if not doc or not doc.get("filename"):
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = doc.get("storage_path")
    if storage_path:
        try:
            content, content_type = _get_storage_object(storage_path)
            return Response(content=content, media_type=doc.get("content_type") or content_type)
        except Exception as e:
            logger.warning("Admin storage fetch failed for %s: %s", storage_path, e)

    filepath = os.path.join(MEDIA_BASE, target_user_id, doc["filename"])
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath, media_type=doc.get("content_type", "image/jpeg"))


@router.post("/kyc/vision-analyze")
async def trigger_vision_analysis(request: Request):
    """Trigger AI Vision analysis on uploaded documents. Returns OCR results."""
    user = await _resolve_user_for_idv(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No KYC submission found")

    docs = kyc.get("documents", [])
    if not docs:
        raise HTTPException(status_code=400, detail="No documents uploaded yet")

    vision_result = await _run_vision_verification(user.user_id, kyc)

    # Store vision results
    await db.afrikpay_kyc.update_one(
        {"user_id": user.user_id},
        {"$set": {"vision_analysis": vision_result, "vision_analyzed_at": datetime.now(timezone.utc).isoformat()}},
    )

    doc_types = {str(d.get("type") or "").lower() for d in docs}
    upload_complete = all(t in doc_types for t in ("id_front", "id_back", "selfie"))
    revoked = False
    if upload_complete:
        revoked = await _revoke_idv_access_token(getattr(user, "idv_access_token", None), "document_upload_completed")

    return {
        "vision_analysis": vision_result,
        "document_upload_complete": upload_complete,
        "idv_access_token_revoked": revoked,
    }


# ── ID Checker ──


class KYCSubmitRequest(BaseModel):
    full_name: str
    date_of_birth: str
    nationality: str
    id_type: str
    id_number: str
    address: str
    phone: str
    level: int = 1

    @validator("full_name")
    def validate_name(cls, v):
        v = v.strip()
        if len(v) < 2 or len(v) > 200:
            raise ValueError("Name must be 2-200 characters")
        return v

    @validator("id_type")
    def validate_id_type(cls, v):
        allowed = {"passport", "national_id", "drivers_license"}
        if v not in allowed:
            raise ValueError(f"ID type must be one of: {', '.join(allowed)}")
        return v

    @validator("nationality")
    def validate_nationality(cls, v):
        if not re.match(r"^[A-Z]{2,3}$", v.upper()):
            raise ValueError("Nationality must be a 2-3 letter country code")
        return v.upper()

    @validator("phone")
    def validate_phone(cls, v):
        cleaned = re.sub(r"[\s\-()]", "", v)
        if not re.match(r"^\+?\d{7,15}$", cleaned):
            raise ValueError("Invalid phone number format")
        return cleaned

    @validator("level")
    def validate_level(cls, v):
        if v not in (1, 2):
            raise ValueError("Level must be 1 or 2")
        return v


class KYCDocumentRequest(BaseModel):
    document_type: str
    document_data: str

    @validator("document_type")
    def validate_doc_type(cls, v):
        allowed = {"id_front", "id_back", "selfie"}
        if v not in allowed:
            raise ValueError(f"Document type must be one of: {', '.join(allowed)}")
        return v

    @validator("document_data")
    def validate_doc_data(cls, v):
        if len(v) > MAX_DOCUMENT_DATA_SIZE:
            raise ValueError(f"Document data exceeds {MAX_DOCUMENT_DATA_SIZE // (1024 * 1024)}MB limit")
        return v


# Automated KYC verification rules
def _auto_verify_kyc(kyc_data: dict) -> dict:
    """Run automated KYC checks. Returns verification result."""
    issues = []
    score = 100

    # Basic field validation
    if not kyc_data.get("full_name") or len(kyc_data["full_name"].strip()) < 3:
        issues.append("Name too short or missing")
        score -= 30

    dob = kyc_data.get("date_of_birth", "")
    if dob:
        try:
            from datetime import datetime as dt

            birth = dt.strptime(dob, "%Y-%m-%d")
            age = (dt.now() - birth).days // 365
            if age < 18:
                issues.append("Must be 18 or older")
                score -= 50
            if age > 120:
                issues.append("Invalid date of birth")
                score -= 40
        except ValueError:
            issues.append("Invalid date format (use YYYY-MM-DD)")
            score -= 20

    if not kyc_data.get("nationality") or len(kyc_data["nationality"]) < 2:
        issues.append("Nationality missing")
        score -= 15

    id_type = kyc_data.get("id_type", "")
    if id_type not in ("passport", "national_id", "drivers_license"):
        issues.append("Invalid ID type")
        score -= 20

    id_number = kyc_data.get("id_number", "")
    if not id_number or len(id_number) < 5:
        issues.append("ID number too short")
        score -= 25

    phone = kyc_data.get("phone", "")
    if not phone or len(phone) < 8:
        issues.append("Phone number invalid")
        score -= 15

    if not kyc_data.get("address") or len(kyc_data["address"].strip()) < 5:
        issues.append("Address too short")
        score -= 10

    # Determine result
    score = max(score, 0)
    if score >= 80 and not issues:
        return {"status": "auto_verified", "score": score, "issues": [], "needs_review": False}
    elif score >= 50:
        return {"status": "pending_review", "score": score, "issues": issues, "needs_review": True}
    else:
        return {"status": "auto_rejected", "score": score, "issues": issues, "needs_review": False}


@router.post("/kyc/submit")
async def submit_kyc(payload: KYCSubmitRequest, request: Request):
    user = await _resolve_user_for_idv(request)

    # Rate limit: max submissions per day
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    daily_count = await db.id_verification_submissions_log.count_documents(
        {
            "user_id": user.user_id,
            "submitted_at": {"$gte": today_start},
        }
    )
    if daily_count >= MAX_SUBMISSIONS_PER_DAY:
        raise HTTPException(
            status_code=429, detail=f"Maximum {MAX_SUBMISSIONS_PER_DAY} submissions per day. Please try again tomorrow."
        )

    existing = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    existing_state = str((existing or {}).get("workflow_state") or _workflow_state_from_legacy_status((existing or {}).get("status"))).upper()
    if existing and existing_state == ID_CHECKER_APPROVED:
        return {"kyc": existing, "message": "Already approved in ID Checker"}

    # Log submission attempt (masked ID for security)
    logger.info(
        f"ID Checker submit: user={user.user_id}, id_type={payload.id_type}, id_masked={_mask_id(payload.id_number)}, country={payload.nationality}"
    )
    await db.id_verification_submissions_log.insert_one(
        {
            "user_id": user.user_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "id_type": payload.id_type,
            "nationality": payload.nationality,
        }
    )

    # Check retry cooldown for rejected submissions
    if existing and existing.get("status") == "rejected":
        first_rejection = existing.get("first_rejection_date")
        if first_rejection:
            rejection_dt = (
                datetime.fromisoformat(first_rejection) if isinstance(first_rejection, str) else first_rejection
            )
            if rejection_dt.tzinfo is None:
                rejection_dt = rejection_dt.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - rejection_dt).days
            if days_since < RETRY_COOLDOWN_DAYS:
                retry_date = (rejection_dt + timedelta(days=RETRY_COOLDOWN_DAYS)).isoformat()
                return {
                    "kyc": existing,
                    "message": f"Retry available after {RETRY_COOLDOWN_DAYS} days from first rejection",
                    "retry_available_date": retry_date,
                    "days_remaining": RETRY_COOLDOWN_DAYS - days_since,
                }

    # Run automated verification
    kyc_data = payload.dict()
    auto_result = _auto_verify_kyc(kyc_data)

    # POLICY LOCK: submissions are never auto-approved.
    # All submissions follow strict ID Checker states.
    if existing_state in {ID_CHECKER_PENDING, ID_CHECKER_AI_REVIEW, ID_CHECKER_ADMIN_REVIEW}:
        raise HTTPException(status_code=409, detail="An ID Checker submission is already in progress")

    if existing_state in {ID_CHECKER_NOT_SUBMITTED, ID_CHECKER_REJECTED, ID_CHECKER_MORE_INFO_REQUIRED}:
        transition = await _transition_id_checker_state(
            user_id=user.user_id,
            current_state=existing_state,
            target_state=ID_CHECKER_PENDING,
            actor="user",
            reason="submission_created",
            metadata={"id_type": payload.id_type, "country": payload.nationality},
        )
    else:
        transition = {
            "workflow_state": ID_CHECKER_PENDING,
            "status": "pending_review",
        }

    status = transition["status"]
    now_iso = datetime.now(timezone.utc).isoformat()
    tier = "pending"

    kyc = {
        "kyc_id": f"idv_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "full_name": encrypt_field(payload.full_name),
        "date_of_birth": encrypt_field(payload.date_of_birth),
        "nationality": payload.nationality,
        "id_type": payload.id_type,
        "id_number_hash": hashlib.sha256(payload.id_number.encode()).hexdigest(),
        "address": encrypt_field(payload.address),
        "phone": payload.phone,
        "level": payload.level,
        "status": status,
        "workflow_state": transition["workflow_state"],
        "tier": tier,
        "auto_verification": auto_result,
        "documents": existing.get("documents", []) if existing else [],
        "submitted_at": now_iso,
        "verified_at": None,
        "verification_method": "manual_review_required",
        "manual_review_required": True,
        "required_documents": sorted(REQUIRED_IDV_DOCUMENT_TYPES),
    }

    # Keep support SLA deadline for manual review
    kyc["support_review_deadline"] = (
        datetime.now(timezone.utc) + timedelta(days=SUPPORT_REVIEW_WINDOW_DAYS)
    ).isoformat()

    if existing:
        await db.afrikpay_kyc.update_one({"user_id": user.user_id}, {"$set": kyc})
    else:
        await db.afrikpay_kyc.insert_one(kyc)
    kyc.pop("_id", None)

    # Create in-app notification + email/SMS log trail
    await _create_idv_notification(
        user_id=user.user_id,
        notif_type="id_checker_submission_received",
        title="ID Checker Submission Received",
        message=(
            f"Your ID Checker submission has been received. "
            f"Upload all required documents (ID front, back, selfie). "
            f"Estimated review SLA: {SUPPORT_REVIEW_WINDOW_DAYS} days."
        ),
        metadata={
            "required_documents": sorted(REQUIRED_IDV_DOCUMENT_TYPES),
            "documents_uploaded": len(kyc.get("documents") or []),
            "rule_score": auto_result.get("score"),
            "rule_result": auto_result.get("status"),
        },
        now_iso=now_iso,
    )
    await _send_idv_status_email(
        user.user_id,
        "pending_review",
        {
            "confidence_score": 0,
            "checks": [],
            "flags": auto_result.get("issues") or ["Awaiting admin manual review"],
        },
        kyc,
    )

    # For pending_review status, check if documents exist and trigger AI verification
    ai_pipeline_result = None
    if status == "pending_review" and kyc.get("documents"):
        doc_types = {d.get("type") for d in kyc.get("documents", [])}
        if REQUIRED_IDV_DOCUMENT_TYPES.issubset(doc_types):
            logger.info(f"Triggering AI verification pipeline for {user.user_id} (has all docs)")
            ai_pipeline_result = await _run_ai_verification_pipeline(user.user_id)
            # Refresh KYC data after AI pipeline
            kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})

    return {"kyc": kyc, "auto_verification": auto_result, "ai_pipeline": ai_pipeline_result}


@router.post("/kyc/document")
async def upload_kyc_document(payload: KYCDocumentRequest, request: Request):
    """Upload an ID Checker document (ID front, back, or selfie).
    Auto-triggers AI verification when all required documents are present."""
    user = await _resolve_user_for_idv(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=400, detail="Submit ID Checker details first")

    doc = {
        "doc_id": f"doc_{uuid.uuid4().hex[:10]}",
        "type": payload.document_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "verified": False,
    }

    current_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()
    if current_state in {ID_CHECKER_MORE_INFO_REQUIRED, ID_CHECKER_REJECTED}:
        pending_state_patch = await _transition_id_checker_state(
            user_id=user.user_id,
            current_state=current_state,
            target_state=ID_CHECKER_PENDING,
            actor="user",
            reason="documents_resubmitted",
            metadata={"document_type": payload.document_type},
        )
    else:
        pending_state_patch = {
            "workflow_state": ID_CHECKER_PENDING,
            "status": "pending_review",
        }

    await db.afrikpay_kyc.update_one(
        {"user_id": user.user_id},
        {
            "$push": {"documents": doc},
            "$set": {
                "level": 2,
                "status": pending_state_patch["status"],
                "workflow_state": pending_state_patch["workflow_state"],
                "tier": "pending",
            },
        },
    )

    # Check if all required documents are now present - trigger AI verification
    updated_kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    all_docs = updated_kyc.get("documents", [])
    doc_types = {d.get("type") for d in all_docs}
    all_required = REQUIRED_IDV_DOCUMENT_TYPES.issubset(doc_types)

    ai_result = None
    if all_required:
        logger.info(f"All documents uploaded for {user.user_id}, triggering AI verification")
        ai_result = await _run_ai_verification_pipeline(user.user_id)

    return {
        "success": True,
        "document": doc,
        "all_documents_uploaded": all_required,
        "required_documents": sorted(REQUIRED_IDV_DOCUMENT_TYPES),
        "missing_documents": sorted(list(REQUIRED_IDV_DOCUMENT_TYPES - doc_types)),
        "ai_verification": ai_result,
        "message": "Document uploaded. AI verification triggered."
        if all_required
        else "Document uploaded. Upload remaining documents to trigger AI verification.",
    }


ALLOWED_FILE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/kyc/upload-file")
async def upload_kyc_file(request: Request, document_type: str = Form(...), file: UploadFile = File(...)):
    """Upload an ID Checker document file. Supports JPG/PNG/WebP/PDF up to 5MB."""
    user = await _resolve_user_for_idv(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=400, detail="Submit ID Checker details first")

    if document_type not in {"id_front", "id_back", "selfie"}:
        raise HTTPException(status_code=400, detail="Document type must be id_front, id_back, or selfie")

    if file.content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Invalid file type: {file.content_type}. Allowed: JPG, PNG, WebP, PDF"
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB")
    if len(content) < 1024:
        raise HTTPException(status_code=400, detail="File too small or empty")

    try:
        security_scan = enforce_file_security(
            content=content,
            claimed_content_type=str(file.content_type or "application/octet-stream"),
            allowed_content_types=ALLOWED_FILE_TYPES,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Document failed security scan")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    filename = f"{doc_id}_{document_type}.{ext}"
    storage_path = f"{ID_CHECKER_STORAGE_PREFIX}/uploads/{user.user_id}/{filename}"
    storage_result = _put_storage_object(storage_path, content, file.content_type or "application/octet-stream")

    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "doc_id": doc_id,
        "type": document_type,
        "filename": filename,
        "original_filename": file.filename,
        "storage_path": storage_result.get("path", storage_path),
        "storage_backend": "object_storage",
        "file_size": len(content),
        "content_type": file.content_type,
        "security_scan": security_scan,
        "uploaded_at": now_iso,
        "verified": False,
    }

    current_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()
    if current_state in {ID_CHECKER_MORE_INFO_REQUIRED, ID_CHECKER_REJECTED}:
        pending_state_patch = await _transition_id_checker_state(
            user_id=user.user_id,
            current_state=current_state,
            target_state=ID_CHECKER_PENDING,
            actor="user",
            reason="documents_resubmitted",
            metadata={"document_type": document_type},
        )
    else:
        pending_state_patch = {
            "workflow_state": ID_CHECKER_PENDING,
            "status": "pending_review",
        }

    # Remove existing doc of same type then add new one
    await db.afrikpay_kyc.update_one({"user_id": user.user_id}, {"$pull": {"documents": {"type": document_type}}})
    await db.afrikpay_kyc.update_one(
        {"user_id": user.user_id},
        {
            "$push": {"documents": doc},
            "$set": {
                "level": 2,
                "status": pending_state_patch["status"],
                "workflow_state": pending_state_patch["workflow_state"],
                "tier": "pending",
            },
        },
    )

    # Check if all required documents are now present
    updated_kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    all_docs = updated_kyc.get("documents", [])
    doc_types = {d.get("type") for d in all_docs}
    all_required = REQUIRED_IDV_DOCUMENT_TYPES.issubset(doc_types)

    ai_result = None
    if all_required:
        logger.info(f"All documents uploaded for {user.user_id}, triggering AI verification")
        ai_result = await _run_ai_verification_pipeline(user.user_id)

    return {
        "success": True,
        "document": doc,
        "all_documents_uploaded": all_required,
        "required_documents": sorted(REQUIRED_IDV_DOCUMENT_TYPES),
        "missing_documents": sorted(list(REQUIRED_IDV_DOCUMENT_TYPES - doc_types)),
        "ai_verification": ai_result,
        "message": "Document uploaded. AI verification triggered."
        if all_required
        else f"Document '{document_type}' uploaded ({len(content) // 1024}KB). Upload remaining documents to trigger AI verification.",
    }


@router.get("/kyc/status")
async def kyc_status(request: Request):
    user = await _resolve_user_for_idv(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    workflow_state = str((kyc or {}).get("workflow_state") or ID_CHECKER_NOT_SUBMITTED)
    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "subscription_plan": 1, "is_admin": 1},
    )
    plan = _normalize_plan_key(
        str((user_doc or {}).get("subscription_plan") or "free"),
        is_admin=bool((user_doc or {}).get("is_admin", False)),
    )
    progress = _workflow_progress_snapshot(workflow_state, (kyc or {}).get("documents") or [])
    sla_meta = _compute_sla_meta((kyc or {}).get("submitted_at"), plan)
    experience_summary = await _build_id_checker_experience_summary(request)
    timeline_summary = await _build_id_checker_transition_summary(user.user_id, workflow_state, sla_meta)

    return {
        "kyc": kyc,
        "entitlements": {
            "plan": plan,
            "service_lane": _service_lane_label(plan),
            "expected_sla_hours": sla_meta.get("expected_sla_hours"),
        },
        "sla": sla_meta,
        "experience_summary": experience_summary,
        "id_checker": {
            "workflow_state": workflow_state,
            "state_label": workflow_state.replace("_", " ").title(),
            "state_progress_pct": progress.get("state_progress_pct"),
            "required_documents": progress.get("required_documents"),
            "uploaded_documents": progress.get("uploaded_documents"),
            "missing_documents": progress.get("missing_documents"),
            "documents_complete": progress.get("documents_complete"),
            "document_progress_pct": progress.get("document_progress_pct"),
            "states": [
                ID_CHECKER_NOT_SUBMITTED,
                ID_CHECKER_PENDING,
                ID_CHECKER_AI_REVIEW,
                ID_CHECKER_ADMIN_REVIEW,
                ID_CHECKER_APPROVED,
                ID_CHECKER_REJECTED,
                ID_CHECKER_MORE_INFO_REQUIRED,
            ],
            "timeline": timeline_summary,
        },
    }


@router.get("/kyc/email-log")
async def kyc_email_log(request: Request):
    """Get notification history (email + SMS) for the user's ID Checker."""
    user = await require_auth(request)
    logs = await db.idv_email_log.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return {"notifications": logs, "total": len(logs)}


@router.get("/kyc/notification-prefs")
async def get_notification_prefs(request: Request):
    """Get user's IDV notification preferences."""
    user = await require_auth(request)
    prefs = await db.idv_notification_prefs.find_one({"user_id": user.user_id}, {"_id": 0})
    return {"preferences": prefs or {"user_id": user.user_id, "email": True, "sms": True}}


@router.put("/kyc/notification-prefs")
async def update_notification_prefs(request: Request):
    """Update user's IDV notification preferences (email/SMS toggles)."""
    user = await require_auth(request)
    body = await request.json()
    email_enabled = body.get("email", True)
    sms_enabled = body.get("sms", True)
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.idv_notification_prefs.update_one(
        {"user_id": user.user_id},
        {"$set": {"email": email_enabled, "sms": sms_enabled, "updated_at": now_iso}},
        upsert=True,
    )
    return {"preferences": {"user_id": user.user_id, "email": email_enabled, "sms": sms_enabled}}


@router.post("/kyc/ai-verify")
async def trigger_ai_verification(request: Request):
    """Manually trigger AI pre-check for the user's pending ID Checker submission."""
    user = await require_auth(request)
    kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No ID Checker submission found")
    workflow_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()
    if workflow_state == ID_CHECKER_APPROVED:
        return {"message": "Already approved", "kyc": kyc}
    if workflow_state == ID_CHECKER_REJECTED and str(kyc.get("status") or "").lower() == "banned":
        raise HTTPException(status_code=403, detail="Account is suspended")
    if not _has_required_idv_documents(kyc):
        raise HTTPException(status_code=400, detail="All required documents (id_front, id_back, selfie) must be uploaded before AI scoring")

    result = await _run_ai_verification_pipeline(user.user_id)
    updated_kyc = await _kyc_find_one({"user_id": user.user_id}, {"_id": 0})
    return {"kyc": updated_kyc, "ai_result": result}


@router.post("/admin/ai-verify/{target_user_id}")
async def admin_trigger_ai_verification(target_user_id: str, request: Request):
    """Admin: Trigger AI pre-check for a specific ID Checker case."""
    await require_admin(request)
    kyc = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No ID Checker record found for this user")
    if not _has_required_idv_documents(kyc):
        raise HTTPException(status_code=400, detail="Cannot run AI scoring: required documents are incomplete")

    result = await _run_ai_verification_pipeline(target_user_id)
    updated_kyc = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0})
    return {"kyc": updated_kyc, "ai_result": result}


@router.get("/admin/ai-analysis/{target_user_id}")
async def admin_get_ai_analysis(target_user_id: str, request: Request):
    """Admin: Get AI analysis details for an ID Checker case."""
    await require_admin(request)
    kyc = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No ID Checker record found")

    return {
        "user_id": target_user_id,
        "status": kyc.get("status"),
        "workflow_state": kyc.get("workflow_state"),
        "ai_verification": kyc.get("ai_verification"),
        "combined_score": kyc.get("combined_score"),
        "verification_method": kyc.get("verification_method"),
        "auto_verification": kyc.get("auto_verification"),
        "ai_verified_at": kyc.get("ai_verified_at"),
    }


@router.get("/admin/queue")
async def admin_id_checker_queue(
    request: Request,
    status: str = "all",
    risk_level: str = "all",
    country: str = "all",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
):
    """Enterprise queue view with status/risk/date/country filters."""
    await require_admin(request)
    query: dict = {}

    st = str(status or "all").strip().upper()
    if st != "ALL":
        if st in {
            ID_CHECKER_NOT_SUBMITTED,
            ID_CHECKER_PENDING,
            ID_CHECKER_AI_REVIEW,
            ID_CHECKER_ADMIN_REVIEW,
            ID_CHECKER_APPROVED,
            ID_CHECKER_REJECTED,
            ID_CHECKER_MORE_INFO_REQUIRED,
        }:
            query["workflow_state"] = st
        else:
            query["status"] = str(status).lower()

    if str(risk_level or "all").lower() != "all":
        query["ai_verification.risk_level"] = str(risk_level).lower()
    if str(country or "all").lower() != "all":
        query["nationality"] = str(country).upper()
    if date_from or date_to:
        submitted_filter = {}
        if date_from:
            submitted_filter["$gte"] = date_from
        if date_to:
            submitted_filter["$lte"] = date_to
        query["submitted_at"] = submitted_filter

    cap = max(1, min(int(limit or 100), 300))
    docs = (
        await _kyc_find_many(
            query,
            {
                "_id": 0,
                "id_number_hash": 0,
            },
            sort=("submitted_at", -1),
            limit=cap,
        )
    )

    user_ids = [str(rec.get("user_id") or "") for rec in docs if rec.get("user_id")]
    user_docs = []
    if user_ids:
        user_docs = await db.users.find(
            {"user_id": {"$in": list(set(user_ids))}},
            {"_id": 0, "user_id": 1, "subscription_plan": 1, "is_admin": 1},
        ).to_list(len(set(user_ids)) + 20)
    plan_map = {
        str(u.get("user_id")): _normalize_plan_key(
            str(u.get("subscription_plan") or "free"),
            is_admin=bool(u.get("is_admin", False)),
        )
        for u in user_docs
    }

    queue = []
    for rec in docs:
        ai = rec.get("ai_verification") or {}
        plan = plan_map.get(str(rec.get("user_id") or ""), "free")
        sla_meta = _compute_sla_meta(rec.get("submitted_at"), plan)
        queue.append(
            {
                "kyc_id": rec.get("kyc_id"),
                "user_id": rec.get("user_id"),
                "full_name": rec.get("full_name"),
                "country": rec.get("nationality"),
                "status": rec.get("status"),
                "workflow_state": rec.get("workflow_state"),
                "submitted_at": rec.get("submitted_at"),
                "updated_at": rec.get("admin_reviewed_at") or rec.get("ai_verified_at") or rec.get("submitted_at"),
                "risk_level": ai.get("risk_level") or "unknown",
                "fraud_risk_score": ai.get("fraud_risk") if ai.get("fraud_risk") is not None else rec.get("combined_score"),
                "ai_confidence": ai.get("confidence_score"),
                "suggested_action": ai.get("recommendation") or ai.get("proposed_decision") or "manual_review",
                "documents_count": len(rec.get("documents") or []),
                "subscription_plan": plan,
                "service_lane": _service_lane_label(plan),
                "sla_due_at": sla_meta.get("sla_due_at"),
                "sla_breached": sla_meta.get("sla_breached"),
                "sla_hours_remaining": sla_meta.get("sla_hours_remaining"),
            }
        )

    return {
        "queue": queue,
        "total": len(queue),
        "filters": {
            "status": status,
            "risk_level": risk_level,
            "country": country,
            "date_from": date_from,
            "date_to": date_to,
        },
    }


@router.get("/admin/queue/stream")
async def admin_id_checker_queue_stream(request: Request, interval_seconds: int = 5):
    """SSE stream for real-time ID Checker queue refresh ticks."""
    await require_admin(request)
    heartbeat = max(3, min(int(interval_seconds or 5), 30))

    async def _aggregate_counts() -> dict:
        state_rows = await db.afrikpay_kyc.aggregate(
            [
                {"$match": {"workflow_state": {"$exists": True, "$ne": None}}},
                {"$group": {"_id": "$workflow_state", "count": {"$sum": 1}}},
            ]
        ).to_list(100)
        risk_rows = await db.afrikpay_kyc.aggregate(
            [
                {
                    "$group": {
                        "_id": {
                            "$toLower": {
                                "$ifNull": ["$ai_verification.risk_level", "unknown"]
                            }
                        },
                        "count": {"$sum": 1},
                    }
                }
            ]
        ).to_list(50)

        state_map = {str(r.get("_id") or "UNKNOWN"): int(r.get("count") or 0) for r in state_rows}
        risk_map = {str(r.get("_id") or "unknown"): int(r.get("count") or 0) for r in risk_rows}

        # Ensure stable keys for frontend
        for key in [
            ID_CHECKER_NOT_SUBMITTED,
            ID_CHECKER_PENDING,
            ID_CHECKER_AI_REVIEW,
            ID_CHECKER_ADMIN_REVIEW,
            ID_CHECKER_APPROVED,
            ID_CHECKER_REJECTED,
            ID_CHECKER_MORE_INFO_REQUIRED,
        ]:
            state_map.setdefault(key, 0)
        for rk in ["low", "medium", "high", "unknown"]:
            risk_map.setdefault(rk, 0)

        return {
            "state_counts": state_map,
            "risk_counts": risk_map,
            "pending_workload": (
                state_map.get(ID_CHECKER_PENDING, 0)
                + state_map.get(ID_CHECKER_AI_REVIEW, 0)
                + state_map.get(ID_CHECKER_ADMIN_REVIEW, 0)
                + state_map.get(ID_CHECKER_MORE_INFO_REQUIRED, 0)
            ),
        }

    async def event_gen():
        while True:
            if await request.is_disconnected():
                break
            agg = await _aggregate_counts()
            payload = {
                "type": "id_checker_queue_tick",
                "ts": datetime.now(timezone.utc).isoformat(),
                **agg,
            }
            yield f"event: queue_tick\ndata: {json.dumps(payload)}\n\n"
            await asyncio.sleep(heartbeat)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/admin/case/{target_user_id}")
async def admin_id_checker_case_detail(target_user_id: str, request: Request):
    """Detailed reviewer payload: docs, OCR fields, AI scores, side-by-side assets."""
    await require_admin(request)
    rec = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0, "id_number_hash": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="ID Checker case not found")

    docs = rec.get("documents") or []
    doc_types = {str(d.get("type") or "").lower() for d in docs}
    front_url = f"/api/id-checker/admin/document-file/{target_user_id}/id_front" if "id_front" in doc_types else None
    selfie_url = f"/api/id-checker/admin/document-file/{target_user_id}/selfie" if "selfie" in doc_types else None

    return {
        "case": rec,
        "document_assets": {
            "id_front": front_url,
            "id_back": f"/api/id-checker/admin/document-file/{target_user_id}/id_back" if "id_back" in doc_types else None,
            "selfie": selfie_url,
            "side_by_side": {
                "left": front_url,
                "right": selfie_url,
            },
        },
        "ocr_extracted": (rec.get("vision_analysis") or {}).get("document_results") or {},
        "ai": {
            "confidence_score": (rec.get("ai_verification") or {}).get("confidence_score"),
            "risk_level": (rec.get("ai_verification") or {}).get("risk_level"),
            "fraud_risk_score": (rec.get("ai_verification") or {}).get("fraud_risk")
            if (rec.get("ai_verification") or {}).get("fraud_risk") is not None
            else rec.get("combined_score"),
            "tampering_flags": (rec.get("vision_analysis") or {}).get("all_issues") or [],
            "suggested_action": (rec.get("ai_verification") or {}).get("recommendation")
            or (rec.get("ai_verification") or {}).get("proposed_decision")
            or "manual_review",
        },
    }


class IDCheckerMessagePayload(BaseModel):
    target_user_id: str
    message: str


@router.post("/messages")
async def id_checker_send_message(payload: IDCheckerMessagePayload, request: Request):
    """Admin/user in-app messaging for ID Checker follow-up."""
    sender = await _resolve_user_for_idv(request)
    target_user_id = payload.target_user_id.strip()
    message = payload.message.strip()
    if len(message) < 2:
        raise HTTPException(status_code=400, detail="Message must be at least 2 characters")

    # Non-admin users can only message admins (or legacy self-target which auto-routes to an admin).
    if not sender.is_admin:
        if target_user_id == sender.user_id:
            default_admin = await db.users.find_one(
                {"$or": [{"is_admin": True}, {"role": "admin"}]},
                {"_id": 0, "user_id": 1},
            )
            if not default_admin or not default_admin.get("user_id"):
                raise HTTPException(status_code=503, detail="No admin recipient available")
            target_user_id = default_admin["user_id"]
        else:
            target_admin = await db.users.find_one(
                {"user_id": target_user_id, "$or": [{"is_admin": True}, {"role": "admin"}]},
                {"_id": 0, "user_id": 1},
            )
            if not target_admin:
                raise HTTPException(status_code=403, detail="Users can only message admin reviewers")

    msg_doc = {
        "message_id": f"idc_msg_{uuid.uuid4().hex[:12]}",
        "from_user_id": sender.user_id,
        "to_user_id": target_user_id,
        "is_admin_message": bool(sender.is_admin),
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.id_checker_messages.insert_one({**msg_doc})
    await _create_idv_notification(
        user_id=target_user_id,
        notif_type="id_checker_message",
        title="ID Checker Message",
        message="You have a new message about your ID Checker submission.",
        metadata={"message_id": msg_doc["message_id"]},
        now_iso=msg_doc["created_at"],
    )
    return {"success": True, "message": msg_doc}


@router.get("/messages/{target_user_id}")
async def id_checker_list_messages(target_user_id: str, request: Request):
    viewer = await _resolve_user_for_idv(request)
    if not viewer.is_admin and viewer.user_id != target_user_id:
        target_admin = await db.users.find_one(
            {"user_id": target_user_id, "$or": [{"is_admin": True}, {"role": "admin"}]},
            {"_id": 0, "user_id": 1},
        )
        if not target_admin:
            raise HTTPException(status_code=403, detail="Not authorized")

    query = {
        "$or": [
            {"from_user_id": viewer.user_id, "to_user_id": target_user_id},
            {"from_user_id": target_user_id, "to_user_id": viewer.user_id},
        ]
    }
    rows = await db.id_checker_messages.find(query, {"_id": 0}).sort("created_at", 1).to_list(300)
    return {"messages": rows, "total": len(rows)}


@router.get("/admin/pending")
async def admin_list_pending_verifications(request: Request, status: str = "ADMIN_REVIEW"):
    """Admin: List all ID Checker submissions by status with AI analysis info."""
    await require_admin(request)
    normalized_status = str(status or "all").strip().upper()
    if normalized_status == "ALL":
        query = {}
    elif normalized_status in {
        ID_CHECKER_NOT_SUBMITTED,
        ID_CHECKER_PENDING,
        ID_CHECKER_AI_REVIEW,
        ID_CHECKER_ADMIN_REVIEW,
        ID_CHECKER_APPROVED,
        ID_CHECKER_REJECTED,
        ID_CHECKER_MORE_INFO_REQUIRED,
    }:
        query = {"workflow_state": normalized_status}
    else:
        query = {"status": str(status).lower()}
    submissions = (
        await _kyc_find_many(query, {"_id": 0, "id_number_hash": 0}, sort=("submitted_at", -1,), limit=100)
    )

    items = []
    for s in submissions:
        items.append(
            {
                "user_id": s.get("user_id"),
                "full_name": s.get("full_name"),
                "status": s.get("status"),
                "workflow_state": s.get("workflow_state"),
                "level": s.get("level"),
                "submitted_at": s.get("submitted_at"),
                "rule_score": s.get("auto_verification", {}).get("score"),
                "ai_confidence": s.get("ai_verification", {}).get("confidence_score")
                if s.get("ai_verification")
                else None,
                "ai_risk_level": s.get("ai_verification", {}).get("risk_level") if s.get("ai_verification") else None,
                "combined_score": s.get("combined_score"),
                "verification_method": s.get("verification_method"),
                "has_ai_analysis": bool(s.get("ai_verification")),
                "documents_count": len(s.get("documents", [])),
            }
        )

    return {
        "submissions": items,
        "total": len(items),
        "filter_status": normalized_status,
    }


class AdminReviewRequest(BaseModel):
    decision: str  # "approve" or "reject" or "more_info_needed"
    reason: Optional[str] = None


@router.post("/admin/review/{target_user_id}")
async def admin_review_verification(target_user_id: str, payload: AdminReviewRequest, request: Request):
    """Admin: Approve/reject/request-more-info for an ID Checker case."""
    admin = await require_admin(request)

    if payload.decision not in ("approve", "reject", "more_info_needed"):
        raise HTTPException(status_code=400, detail="Decision must be 'approve', 'reject', or 'more_info_needed'")

    kyc = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="No ID Checker record found")

    current_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()
    if current_state != ID_CHECKER_ADMIN_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Case must be in {ID_CHECKER_ADMIN_REVIEW} before final admin decision",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "admin_reviewed_by": admin.user_id,
        "admin_reviewed_at": now_iso,
        "admin_decision": payload.decision,
        "admin_reason": payload.reason or "",
    }

    target_state = (
        ID_CHECKER_APPROVED
        if payload.decision == "approve"
        else ID_CHECKER_REJECTED
        if payload.decision == "reject"
        else ID_CHECKER_MORE_INFO_REQUIRED
    )
    state_patch = await _transition_id_checker_state(
        user_id=target_user_id,
        current_state=current_state,
        target_state=target_state,
        actor=f"admin:{admin.user_id}",
        reason="manual_admin_decision",
        metadata={"decision": payload.decision},
    )
    update["workflow_state"] = state_patch["workflow_state"]
    update["status"] = state_patch["status"]

    if payload.decision == "approve":
        update["tier"] = "verified"
        update["verified_at"] = now_iso
    elif payload.decision == "reject":
        update["tier"] = "rejected"
        update["rejection_reason"] = payload.reason or "Rejected by admin"
    else:
        update["tier"] = "pending"
        update["more_info_needed"] = True
        update["more_info_notes"] = payload.reason or "Please provide additional supporting information for your verification."
        update["support_review_deadline"] = (datetime.now(timezone.utc) + timedelta(days=SUPPORT_REVIEW_WINDOW_DAYS)).isoformat()

    await db.afrikpay_kyc.update_one({"user_id": target_user_id}, {"$set": update})
    updated_kyc = await _kyc_find_one({"user_id": target_user_id}, {"_id": 0})

    # Keep user profile gate aligned with final/admin decision.
    if payload.decision == "approve":
        await db.users.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "kyc_verified": True,
                    "kyc_tier": updated_kyc.get("tier", "level_1") if updated_kyc else "level_1",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    elif payload.decision in {"reject", "more_info_needed"}:
        await db.users.update_one(
            {"user_id": target_user_id},
            {
                "$set": {
                    "kyc_verified": False,
                    "kyc_tier": "pending" if payload.decision == "more_info_needed" else "unverified",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    # Send notification to user
    try:
        user = await db.users.find_one({"user_id": target_user_id}, {"_id": 0, "email": 1, "name": 1})
        if user:
            if payload.decision == "approve":
                notif_title = "Identity Verified"
                notif_body = "Your ID Checker case is approved. You now have full access."
            elif payload.decision == "reject":
                notif_title = "Verification Rejected"
                notif_body = f"Your ID Checker case was rejected: {payload.reason or 'Please contact support@realaicoach.app.'}"
            else:
                notif_title = "More Information Needed"
                notif_body = "More information is required for your ID Checker case. Please review your email or contact support@realaicoach.app."
            await _create_idv_notification(
                user_id=target_user_id,
                notif_type="idv_more_info_needed" if payload.decision == "more_info_needed" else f"idv_{payload.decision}d",
                title=notif_title,
                message=notif_body,
                now_iso=now_iso,
            )

            ai_result = updated_kyc.get("ai_verification", {}) if updated_kyc else {}
            if not ai_result:
                ai_result = {
                    "checks": [],
                    "confidence_score": 0,
                    "flags": [payload.reason or "Admin verification decision"],
                }
            status_map = {
                "approve": "verified",
                "reject": "rejected",
                "more_info_needed": "more_info_needed",
            }
            await _send_idv_status_email(target_user_id, status_map[payload.decision], ai_result, updated_kyc or update)
    except Exception as e:
        logger.warning(f"Failed to send IDV review notification: {e}")

    return {
        "success": True,
        "decision": payload.decision,
        "user_id": target_user_id,
        "kyc": updated_kyc,
    }


@router.get("/admin/stats")
async def admin_idv_stats(request: Request):
    """Admin: Get ID Checker statistics."""
    await require_admin(request)
    return await build_admin_stats_payload(db)


class ManualReviewPolicyEnforcementRequest(BaseModel):
    dry_run: bool = True
    limit: int = 500


@router.get("/admin/policy/manual-review-violations")
async def admin_list_manual_review_violations(request: Request, limit: int = 200):
    """List verified records that lack manual admin-review attribution."""
    await require_admin(request)
    cap = max(1, min(limit, 2000))
    rows = await _kyc_find_many(
        _manual_review_violation_query(),
        {
            "_id": 0,
            "kyc_id": 1,
            "user_id": 1,
            "status": 1,
            "tier": 1,
            "submitted_at": 1,
            "verified_at": 1,
            "verification_method": 1,
            "admin_reviewed_by": 1,
            "verified_by": 1,
            "documents": 1,
            "auto_verification": 1,
            "combined_score": 1,
        },
        sort=("verified_at", -1),
        limit=cap,
    )
    items = []
    for row in rows:
        items.append(
            {
                "kyc_id": row.get("kyc_id"),
                "user_id": row.get("user_id"),
                "status": row.get("status"),
                "tier": row.get("tier"),
                "submitted_at": row.get("submitted_at"),
                "verified_at": row.get("verified_at"),
                "verification_method": row.get("verification_method"),
                "documents_count": len(row.get("documents") or []),
                "auto_status": (row.get("auto_verification") or {}).get("status"),
                "auto_score": (row.get("auto_verification") or {}).get("score"),
                "combined_score": row.get("combined_score"),
            }
        )
    return {
        "total": len(items),
        "violations": items,
        "policy": "All verified IDV must include manual admin review attribution.",
    }


@router.post("/admin/policy/enforce-manual-review")
async def admin_enforce_manual_review_policy(payload: ManualReviewPolicyEnforcementRequest, request: Request):
    """Demote non-manually-attributed verified records to pending_review for admin re-review."""
    admin = await require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    cap = max(1, min(payload.limit, 5000))

    violations = await _kyc_find_many(
        _manual_review_violation_query(),
        {"_id": 0},
        sort=("verified_at", -1),
        limit=cap,
    )

    if payload.dry_run:
        return {
            "dry_run": True,
            "would_remediate": len(violations),
            "sample_user_ids": [v.get("user_id") for v in violations[:20]],
        }

    remediated = 0
    for kyc in violations:
        uid = kyc.get("user_id")
        if not uid:
            continue

        current_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()
        transition = await _transition_id_checker_state(
            user_id=uid,
            current_state=current_state,
            target_state=ID_CHECKER_PENDING,
            actor=f"admin:{admin.user_id}",
            reason="policy_enforce_manual_rereview",
        )

        update = {
            "status": transition["status"],
            "workflow_state": transition["workflow_state"],
            "tier": "pending",
            "verified_at": None,
            "manual_review_required": True,
            "policy_remediated_at": now_iso,
            "policy_remediated_by": admin.user_id,
            "policy_remediation_reason": "verified_without_manual_admin_review",
            "verification_method": "manual_review_required_reverification",
        }

        await db.afrikpay_kyc.update_one({"user_id": uid}, {"$set": update})
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {"kyc_verified": False, "kyc_tier": "pending", "updated_at": datetime.now(timezone.utc)}},
        )
        await _create_idv_notification(
            user_id=uid,
            notif_type="id_checker_admin_review",
            title="ID Checker Requires Manual Re-Review",
            message="Your verification has been moved to admin manual review due to policy enforcement. You will be notified once an admin decision is completed.",
            metadata={"policy": "manual_review_required", "reason": "verified_without_manual_admin_review"},
            now_iso=now_iso,
        )

        await _send_idv_status_email(
            uid,
            "pending_review",
            {
                "confidence_score": 0,
                "checks": [],
                "flags": ["Policy enforcement: manual admin review required"],
            },
            {**kyc, **update},
        )

        await db.admin_audit_logs.insert_one(
            {
                "event_id": f"idv_policy_enforce_{uuid.uuid4().hex[:10]}",
                "user_id": admin.user_id,
                "action": "id_checker_policy_enforce_manual_review",
                "target_user_id": uid,
                "reason": "verified_without_manual_admin_review",
                "created_at": now_iso,
            }
        )
        remediated += 1

    return {
        "dry_run": False,
        "remediated": remediated,
        "requested_limit": cap,
    }


# ── QR Code Desktop-to-Mobile Verification ──

QR_SESSION_EXPIRY_MINUTES = 2


@router.post("/qr/create")
async def create_qr_session(request: Request):
    """Create a QR verification session for desktop users. Returns a session_id for the QR code."""
    user = await _resolve_user_for_idv(request)
    session_id = f"qr_{uuid.uuid4().hex[:16]}"
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    session = {
        "session_id": session_id,
        "user_id": user.user_id,
        "token": token,
        "status": "pending",  # pending, uploading, complete, expired
        "documents": {},
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=QR_SESSION_EXPIRY_MINUTES)).isoformat(),
    }
    await db.id_verification_qr_sessions.insert_one(session)
    return {"session_id": session_id, "token": token, "expires_in": QR_SESSION_EXPIRY_MINUTES * 60}


@router.get("/qr/status/{session_id}")
async def qr_session_status(session_id: str, request: Request):
    """Poll for QR session completion from desktop."""
    user = await _resolve_user_for_idv(request)
    session = await db.id_verification_qr_sessions.find_one(
        {"session_id": session_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check expiry
    expires = datetime.fromisoformat(session["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires and session["status"] == "pending":
        await db.id_verification_qr_sessions.update_one({"session_id": session_id}, {"$set": {"status": "expired"}})
        session["status"] = "expired"

    return {
        "session_id": session_id,
        "status": session["status"],
        "documents": session.get("documents", {}),
    }


@router.get("/qr/mobile/{session_id}")
async def qr_mobile_info(session_id: str, token: str):
    """Get session info for mobile verification page. No auth needed - uses token."""
    session = await db.id_verification_qr_sessions.find_one({"session_id": session_id, "token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Invalid session")

    # Check expiry
    expires = datetime.fromisoformat(session["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        return {"valid": False, "reason": "Session expired"}

    if session["status"] == "complete":
        return {"valid": False, "reason": "Session already completed"}

    return {"valid": True, "session_id": session_id, "status": session["status"]}


class QRDocumentUpload(BaseModel):
    document_type: str
    document_data: str

    @validator("document_type")
    def validate_doc_type(cls, v):
        allowed = {"id_front", "id_back", "selfie"}
        if v not in allowed:
            raise ValueError(f"Document type must be one of: {', '.join(allowed)}")
        return v

    @validator("document_data")
    def validate_doc_data(cls, v):
        if len(v) > MAX_DOCUMENT_DATA_SIZE:
            raise ValueError("Document data exceeds size limit")
        return v


@router.post("/qr/upload/{session_id}")
async def qr_upload_document(session_id: str, token: str, payload: QRDocumentUpload):
    """Upload a document from mobile via QR session. No auth needed - uses token."""
    session = await db.id_verification_qr_sessions.find_one({"session_id": session_id, "token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Invalid session")

    # Check expiry - extend expiry during upload phase
    expires = datetime.fromisoformat(session["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires and session["status"] == "pending":
        raise HTTPException(status_code=410, detail="Session expired")

    now_iso = datetime.now(timezone.utc).isoformat()
    doc_key = payload.document_type
    update = {
        f"documents.{doc_key}": {
            "uploaded_at": now_iso,
            "size": len(payload.document_data),
        },
        "status": "uploading",
        # Extend expiry by 5 min once uploading starts
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    await db.id_verification_qr_sessions.update_one({"session_id": session_id}, {"$set": update})

    return {"success": True, "document_type": doc_key}


@router.post("/qr/complete/{session_id}")
async def qr_complete_session(session_id: str, token: str):
    """Mark QR session as complete. Called from mobile after all uploads."""
    session = await db.id_verification_qr_sessions.find_one({"session_id": session_id, "token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Invalid session")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.id_verification_qr_sessions.update_one(
        {"session_id": session_id}, {"$set": {"status": "complete", "completed_at": now_iso}}
    )

    # Also save documents to the user's KYC record
    user_id = session["user_id"]
    docs = session.get("documents", {})
    doc_records = []
    for doc_type, doc_info in docs.items():
        doc_records.append(
            {
                "doc_id": f"doc_{uuid.uuid4().hex[:10]}",
                "type": doc_type,
                "uploaded_at": doc_info.get("uploaded_at", now_iso),
                "verified": False,
                "source": "qr_mobile",
            }
        )

    if doc_records:
        await db.afrikpay_kyc.update_one(
            {"user_id": user_id},
            {
                "$push": {"documents": {"$each": doc_records}},
                "$set": {
                    "level": 2,
                    "status": "pending_review",
                    "workflow_state": ID_CHECKER_PENDING,
                    "tier": "pending",
                },
            },
        )

    return {"success": True, "documents_synced": len(doc_records)}


# ── Admin ID Checker Dashboard ──


@router.get("/admin/dashboard")
async def admin_id_verification_dashboard(request: Request):
    """Admin dashboard with stats on ID Checker cases."""
    await require_admin(request)
    dashboard = await build_admin_dashboard_payload(db)
    dashboard["operations_kpis"] = await _build_id_checker_operations_kpis(30)
    dashboard["conversion_funnel"] = await _build_id_checker_conversion_funnel(30)
    return dashboard


@router.get("/admin/operations-kpis")
async def admin_id_checker_operations_kpis(request: Request, lookback_days: int = 30):
    """Admin operations metrics used by enterprise ID Checker queue and conversion monitoring."""
    await require_admin(request)
    return await _build_id_checker_operations_kpis(lookback_days)


@router.get("/admin/conversion-funnel")
async def admin_id_checker_conversion_funnel(request: Request, lookback_days: int = 30):
    """Conversion funnel analytics for enterprise ID Checker commercialization monitoring."""
    await require_admin(request)
    return await _build_id_checker_conversion_funnel(lookback_days)


@router.get("/experience-summary")
async def id_checker_experience_summary(request: Request):
    """User-facing premium status summary with plan lane and trust readiness nudges."""
    return await _build_id_checker_experience_summary(request)


class AdminOverrideRequest(BaseModel):
    user_id: str
    action: str  # force_approve, force_reject, extend_review, request_more_info, ban
    reason: Optional[str] = None


@router.post("/admin/override")
async def admin_override_verification(payload: AdminOverrideRequest, request: Request):
    """Admin override for ID Checker with audited state transitions."""
    admin = await require_admin(request)

    kyc = await _kyc_find_one({"user_id": payload.user_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="ID Checker record not found")

    current_state = str(kyc.get("workflow_state") or _workflow_state_from_legacy_status(kyc.get("status"))).upper()

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {"admin_override_at": now_iso, "admin_override_by": admin.user_id}

    if payload.action == "force_approve":
        state_patch = await _transition_id_checker_state(
            user_id=payload.user_id,
            current_state=current_state,
            target_state=ID_CHECKER_APPROVED,
            actor=f"admin:{admin.user_id}",
            reason="admin_override_force_approve",
        )
        update["status"] = state_patch["status"]
        update["workflow_state"] = state_patch["workflow_state"]
        update["tier"] = f"level_{kyc.get('level', 1)}"
        update["verified_at"] = now_iso
        await db.users.update_one(
            {"user_id": payload.user_id},
            {"$set": {"kyc_verified": True, "kyc_tier": update["tier"], "updated_at": datetime.now(timezone.utc)}},
        )
    elif payload.action == "force_reject":
        state_patch = await _transition_id_checker_state(
            user_id=payload.user_id,
            current_state=current_state,
            target_state=ID_CHECKER_REJECTED,
            actor=f"admin:{admin.user_id}",
            reason="admin_override_force_reject",
        )
        update["status"] = state_patch["status"]
        update["workflow_state"] = state_patch["workflow_state"]
        update["tier"] = "unverified"
        update["rejection_reason"] = payload.reason or "Admin rejected"
        update["first_rejection_date"] = kyc.get("first_rejection_date", now_iso)
        update["last_rejection_date"] = now_iso
        update["retry_available_date"] = (datetime.now(timezone.utc) + timedelta(days=RETRY_COOLDOWN_DAYS)).isoformat()
        await db.users.update_one(
            {"user_id": payload.user_id},
            {"$set": {"kyc_verified": False, "kyc_tier": "unverified", "updated_at": datetime.now(timezone.utc)}},
        )
    elif payload.action in ("extend_review", "request_more_info"):
        if payload.action == "request_more_info":
            state_patch = await _transition_id_checker_state(
                user_id=payload.user_id,
                current_state=current_state,
                target_state=ID_CHECKER_MORE_INFO_REQUIRED,
                actor=f"admin:{admin.user_id}",
                reason="admin_override_more_info",
            )
        else:
            # keep inside active review loop
            target_state = ID_CHECKER_PENDING if current_state == ID_CHECKER_MORE_INFO_REQUIRED else ID_CHECKER_ADMIN_REVIEW
            if current_state != target_state:
                state_patch = await _transition_id_checker_state(
                    user_id=payload.user_id,
                    current_state=current_state,
                    target_state=target_state,
                    actor=f"admin:{admin.user_id}",
                    reason="admin_override_extend_review",
                )
            else:
                state_patch = {
                    "workflow_state": target_state,
                    "status": _legacy_status_from_workflow_state(target_state),
                }
        update["status"] = state_patch["status"]
        update["workflow_state"] = state_patch["workflow_state"]
        update["tier"] = "pending"
        update["more_info_needed"] = True if payload.action == "request_more_info" else update.get("more_info_needed", False)
        update["more_info_notes"] = payload.reason or "Additional information may be needed for final verification."
        update["support_review_deadline"] = (
            datetime.now(timezone.utc) + timedelta(days=SUPPORT_REVIEW_WINDOW_DAYS)
        ).isoformat()
        await db.users.update_one(
            {"user_id": payload.user_id},
            {"$set": {"kyc_verified": False, "kyc_tier": "pending", "updated_at": datetime.now(timezone.utc)}},
        )
    elif payload.action == "ban":
        state_patch = await _transition_id_checker_state(
            user_id=payload.user_id,
            current_state=current_state,
            target_state=ID_CHECKER_REJECTED,
            actor=f"admin:{admin.user_id}",
            reason="admin_override_suspend_for_fraud",
            metadata={"suspended": True},
        )
        update["status"] = "banned"
        update["workflow_state"] = state_patch["workflow_state"]
        update["ban_reason"] = payload.reason or "Fraudulent activity"
        await db.users.update_one(
            {"user_id": payload.user_id},
            {"$set": {"is_banned": True, "ban_reason": payload.reason, "updated_at": datetime.now(timezone.utc)}},
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await db.afrikpay_kyc.update_one({"user_id": payload.user_id}, {"$set": update})

    # Audit log
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"idv_override_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": f"id_verification_override_{payload.action}",
            "target_user_id": payload.user_id,
            "reason": payload.reason,
            "created_at": now_iso,
        }
    )

    # Send email notification for admin overrides
    if payload.action in ("force_approve", "force_reject", "request_more_info"):
        ai_result = kyc.get("ai_verification", {})
        if not ai_result:
            ai_result = {"checks": [], "confidence_score": 0, "flags": [payload.reason or "Admin decision"]}
        status_map = {"force_approve": "verified", "force_reject": "rejected", "request_more_info": "more_info_needed"}
        await _send_idv_status_email(payload.user_id, status_map[payload.action], ai_result, {**kyc, **update})

    return {"success": True, "action": payload.action, "user_id": payload.user_id}


@router.get("/admin/export/csv")
async def export_csv(request: Request):
    """Export ID Checker data as CSV."""
    from fastapi.responses import StreamingResponse

    await require_admin(request)
    filename, csv_text = await render_idv_export_csv(kyc_find_many=_kyc_find_many)

    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/admin/export/pdf")
async def export_pdf(request: Request):
    """Export ID Checker report as PDF."""
    from fastapi.responses import StreamingResponse

    await require_admin(request)
    filename, pdf_bytes = await render_idv_export_pdf(
        db=db,
        enforce_pdf=_enforce_pdf_v15_enterprise,
        build_pdf_filename=build_pdf_v15_filename,
    )

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── AML Monitoring ──


@router.post("/fraud/analyze")
async def analyze_transaction_fraud(request: Request):
    """Run AI fraud analysis on a transaction (admin or system use)."""
    user = await require_auth(request)
    body = await request.json()

    rule_result = await enhanced_fraud_check(user.user_id, body)
    ai_result = await ai_fraud_analysis(user.user_id, body)

    combined_score = round((rule_result["risk_score"] * 0.4 + ai_result.get("ai_score", 0.1) * 0.6), 3)
    recommendation = "approve"
    if combined_score > 0.7:
        recommendation = "block"
    elif combined_score > 0.4:
        recommendation = "review"

    return {
        "combined_risk_score": combined_score,
        "recommendation": recommendation,
        "rule_based": rule_result,
        "ai_analysis": ai_result,
    }


@router.get("/fraud/dashboard")
async def fraud_dashboard(request: Request):
    """Admin fraud detection dashboard with stats."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()
    (now - timedelta(days=30)).isoformat()

    total_flags = await db.afrikpay_fraud_flags.count_documents({})
    pending_flags = await db.afrikpay_fraud_flags.count_documents({"status": "pending_review"})
    resolved_flags = await db.afrikpay_fraud_flags.count_documents({"status": {"$in": ["cleared", "confirmed_fraud"]}})

    recent_flags = await db.afrikpay_fraud_flags.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)

    # AML stats
    aml_total = await db.afrikpay_aml_flags.count_documents({})
    aml_pending = await db.afrikpay_aml_flags.count_documents({"status": "pending_review"})

    # High-risk transactions (risk_score > 0.5)
    high_risk_txs = (
        await db.afrikpay_transactions.find(
            {"risk_score": {"$gt": 0.5}},
            {"_id": 0, "tx_id": 1, "type": 1, "amount": 1, "risk_score": 1, "sender_id": 1, "created_at": 1},
        )
        .sort("risk_score", -1)
        .to_list(10)
    )

    # Frozen accounts
    frozen = await db.afrikpay_wallets.count_documents({"status": "frozen"})

    # Recent 7-day trend
    daily_fraud_pipe = [
        {"$match": {"created_at": {"$gte": seven_days}}},
        {"$addFields": {"date": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {"_id": "$date", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    daily_trend = await db.afrikpay_fraud_flags.aggregate(daily_fraud_pipe).to_list(7)

    return {
        "summary": {
            "total_flags": total_flags,
            "pending_review": pending_flags,
            "resolved": resolved_flags,
            "aml_flags": aml_total,
            "aml_pending": aml_pending,
            "frozen_accounts": frozen,
        },
        "recent_flags": recent_flags,
        "high_risk_transactions": high_risk_txs,
        "daily_trend": daily_trend,
    }


@router.get("/aml/flags")
async def get_aml_flags(request: Request):
    await require_admin(request)
    flags = await db.afrikpay_aml_flags.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"flags": flags}


@router.post("/aml/resolve/{aml_id}")
async def resolve_aml_flag(aml_id: str, request: Request):
    admin = await require_admin(request)
    body = await request.json()
    action = body.get("action", "cleared")

    result = await db.afrikpay_aml_flags.update_one(
        {"aml_id": aml_id},
        {
            "$set": {
                "status": action,
                "resolved_by": admin.user_id,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="AML flag not found")
    return {"success": True}


@router.get("/admin/kyc")
async def admin_kyc_list(request: Request):
    await require_admin(request)
    kycs = await _kyc_find_many({}, {"_id": 0}, sort=("submitted_at", -1,), limit=50)

    # Enrich with user info
    for kyc in kycs:
        w = await db.afrikpay_wallets.find_one({"user_id": kyc["user_id"]}, {"_id": 0, "handle": 1, "user_email": 1})
        if w:
            kyc["handle"] = w.get("handle")
            kyc["email"] = w.get("user_email")

    stats = {
        "total": len(kycs),
        "pending": len([k for k in kycs if k.get("status") == "pending_review"]),
        "verified": len([k for k in kycs if k.get("status") == "verified"]),
        "rejected": len([k for k in kycs if k.get("status") == "rejected"]),
    }
    return {"kyc_submissions": kycs, "stats": stats}


@router.post("/admin/kyc/{kyc_id}/verify")
async def verify_kyc(kyc_id: str, request: Request):
    admin = await require_admin(request)
    body = await request.json()
    action = str(body.get("action", "verified") or "verified").strip().lower()
    if action not in {"verified", "rejected", "pending_review"}:
        raise HTTPException(status_code=400, detail="Action must be verified, rejected, or pending_review")

    kyc = await _kyc_find_one({"kyc_id": kyc_id}, {"_id": 0})
    if not kyc:
        raise HTTPException(status_code=404, detail="KYC submission not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "status": action,
        "verified_by": admin.user_id,
        "admin_reviewed_by": admin.user_id,
        "admin_reviewed_at": now_iso,
        "admin_decision": "approve" if action == "verified" else "reject" if action == "rejected" else "more_info_needed",
        "tier": f"level_{kyc.get('level', 1)}" if action == "verified" else "unverified" if action == "rejected" else "pending",
        "verification_method": "admin_manual_review",
    }
    if action == "verified":
        update["verified_at"] = now_iso
    if action == "rejected":
        update["rejection_reason"] = body.get("reason") or "Rejected by admin"

    await db.afrikpay_kyc.update_one({"kyc_id": kyc_id}, {"$set": update})

    await db.users.update_one(
        {"user_id": kyc.get("user_id")},
        {
            "$set": {
                "kyc_verified": action == "verified",
                "kyc_tier": update["tier"],
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    await _create_idv_notification(
        user_id=kyc.get("user_id"),
        notif_type=f"id_verification_{action}",
        title="ID Checker Approved" if action == "verified" else "ID Checker Rejected" if action == "rejected" else "ID Checker Pending Review",
        message="Your identity has been verified by admin manual review." if action == "verified" else "Your verification was rejected by admin review." if action == "rejected" else "Your verification requires additional admin review.",
        now_iso=now_iso,
    )

    ai_result = (kyc.get("ai_verification") or {"checks": [], "confidence_score": 0, "flags": []})
    status_for_email = "verified" if action == "verified" else "rejected" if action == "rejected" else "pending_review"
    await _send_idv_status_email(kyc.get("user_id"), status_for_email, ai_result, {**kyc, **update})

    return {"success": True, "status": action, "kyc_id": kyc_id}


# ── Admin Super Dashboard Data ──


@router.get("/admin/super-dashboard")
async def admin_super_dashboard(request: Request):
    """Consolidated admin dashboard for all AfrikPay systems."""
    await require_admin(request)
    return await build_admin_super_dashboard_payload(db)


# ── Scheduled Job: Auto-unlock IDV re-verification ──


async def auto_unlock_idv_reverification():
    """Background job: Notify users when their 14-day IDV re-verification cooldown has expired."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    expired = await db.afrikpay_kyc.find(
        {
            "status": "rejected",
            "retry_available_date": {"$lte": now_iso, "$ne": None},
            "reverify_notified": {"$ne": True},
        },
        {"_id": 0, "user_id": 1, "kyc_id": 1},
    ).to_list(50)

    for kyc in expired:
        try:
            await db.afrikpay_kyc.update_one(
                {"user_id": kyc["user_id"], "status": "rejected"},
                {"$set": {"reverify_notified": True, "updated_at": now_iso}},
            )
            from routes.notification_engine import emit_notification

            await emit_notification(
                user_id=kyc["user_id"],
                notif_type="idv_reverify_available",
                title="ID Re-Verification Available",
                body="Your ID Checker cooldown has expired. You can now resubmit your identity documents.",
                action_url="/subscription/kyc",
            )
            # Send email
            user_doc = await db.users.find_one({"user_id": kyc["user_id"]}, {"_id": 0, "email": 1, "name": 1})
            if user_doc and user_doc.get("email"):
                from utils.email_service import is_email_configured

                if is_email_configured():
                    from utils.email_service import send_catalog_template
                    await send_catalog_template(
                        recipient_email=user_doc["email"],
                        template_key="idv_reverification",
                        user_name=user_doc.get("name", "there"),
                    )
            logger.info(f"IDV auto-unlock notification sent for user {kyc['user_id']}")
        except Exception as e:
            logger.error(f"IDV auto-unlock failed for {kyc.get('user_id')}: {e}")

    return len(expired)
