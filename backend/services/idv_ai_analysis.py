"""ID Verification AI Analysis Service.
Extracted from id_verification.py for modularity."""

import logging
from datetime import datetime, timezone
from routes.db import db
from utils.llm_helper import generate_verified_json

logger = logging.getLogger(__name__)


def _calc_account_age(user: dict) -> int:
    if not user or not user.get("created_at"):
        return 0
    try:
        created = user["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created).days
    except Exception:
        return 0


async def ai_verify_kyc_submission(kyc_data: dict, user_id: str) -> dict:
    """Run AI-powered verification analysis on a KYC submission."""
    try:
        user = await db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "created_at": 1, "email": 1, "subscription_plan": 1}
        )
        past_submissions = await db.id_verification_submissions_log.count_documents({"user_id": user_id})
        past_rejections = await db.afrikpay_kyc.count_documents({"user_id": user_id, "status": "rejected"})
        await db.login_sessions.count_documents(
            {"user_id": user_id}
        ) if "login_sessions" in await db.list_collection_names() else 0

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

        system_msg = """You are an expert ID verification analyst for a fintech platform operating in Africa.
Analyze the submitted identity verification data for authenticity, consistency, and fraud risk.
Consider: name-nationality consistency, phone format matching country, age appropriateness,
address format, document completeness, submission patterns, and behavioral signals."""

        prompt = f"""Analyze this ID verification submission and return a JSON assessment.

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
- Duplicate ID detected: {context["duplicate_id_detected"]}
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
        logger.warning(f"AI ID verification analysis error for {user_id}: {e}")

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
