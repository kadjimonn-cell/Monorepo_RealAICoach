"""ID Verification Notification Service.
Handles email and SMS notifications for IDV status changes."""

import logging
from datetime import datetime, timezone
from routes.db import db
from utils.email_templates import (
    build_idv_approved_email,
    build_idv_rejected_email,
    build_idv_pending_review_email,
)

logger = logging.getLogger(__name__)


async def send_idv_status_email(user_id: str, status: str, ai_result: dict, kyc: dict):
    """Send email + SMS notifications for ID verification status changes."""
    try:
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
        if not user or not user.get("email"):
            return
        user_name = user.get("name", "User")
        user_email = user["email"]
        phone = kyc.get("phone", "")
        checks = ai_result.get("checks", [])
        confidence = ai_result.get("confidence_score", 0)
        flags = ai_result.get("flags", [])
        now_iso = datetime.now(timezone.utc).isoformat()

        prefs = await db.idv_notification_prefs.find_one({"user_id": user_id}, {"_id": 0})
        email_enabled = prefs.get("email", True) if prefs else True
        sms_enabled = prefs.get("sms", True) if prefs else True

        tpl = None
        sms_text = ""
        if status == "verified":
            tpl = build_idv_approved_email(
                user_name=user_name,
                tier=kyc.get("tier", "level_1"),
                checks_passed=sum(1 for c in checks if c.get("passed")),
                total_checks=len(checks),
                confidence=confidence,
            )
            sms_text = f"RealAICoach: Your identity has been verified! AI Confidence: {round(confidence * 100)}%. You now have full platform access."
        elif status == "rejected":
            retry_date = kyc.get("retry_available_date", "N/A")
            if retry_date != "N/A":
                try:
                    retry_date = datetime.fromisoformat(retry_date).strftime("%B %d, %Y")
                except (ValueError, TypeError):
                    pass
            tpl = build_idv_rejected_email(
                user_name=user_name,
                reasons=flags or ["Further review required"],
                flags=flags,
                retry_date=retry_date,
            )
            sms_text = f"RealAICoach: Your ID verification was declined. You may retry after {retry_date}. Check your email for details."
        elif status == "pending_review":
            tpl = build_idv_pending_review_email(
                user_name=user_name,
                ai_confidence=confidence if confidence > 0 else None,
                flags=flags if flags else None,
            )
            sms_text = "RealAICoach: Your ID verification is under review. Estimated: 1-2 business days. We'll notify you of the result."
        else:
            return

        email_result = {"success": False, "error": "disabled"}
        if email_enabled and tpl:
            from utils.email_service import send_catalog_template
            idv_template_map = {"verified": "idv_approved", "rejected": "idv_rejected", "pending_review": "idv_pending"}
            tpl_key = idv_template_map.get(status)
            if tpl_key:
                idv_kwargs = {"user_name": user_name}
                if status == "verified":
                    idv_kwargs.update(tier=kyc.get("tier", "level_1"), checks_passed=sum(1 for c in checks if c.get("passed")), total_checks=len(checks), confidence=confidence)
                elif status == "rejected":
                    idv_kwargs.update(reasons=flags or ["Further review required"], flags=flags, retry_date=retry_date)
                elif status == "pending_review":
                    idv_kwargs.update(ai_confidence=confidence if confidence > 0 else None, flags=flags if flags else None)
                email_result = await send_catalog_template(user_email, tpl_key, user_name, **idv_kwargs)
            if email_result.get("success"):
                logger.info(f"IDV email sent to {user_email}: {tpl.subject}")
            else:
                logger.warning(f"IDV email failed for {user_email}: {email_result.get('error')}")

        await db.idv_email_log.insert_one(
            {
                "user_id": user_id,
                "channel": "email",
                "email": user_email,
                "status": status,
                "subject": tpl.subject if tpl else "",
                "sent": email_result.get("success", False),
                "error": email_result.get("error") if not email_result.get("success") else None,
                "created_at": now_iso,
            }
        )

        sms_result = {"success": False, "error": "disabled"}
        if sms_enabled and phone and sms_text:
            sms_result = {"success": False, "error": "SMS has been removed from this platform"}

        if phone:
            await db.idv_email_log.insert_one(
                {
                    "user_id": user_id,
                    "channel": "sms",
                    "phone": phone,
                    "status": status,
                    "subject": sms_text[:60] + "..." if len(sms_text) > 60 else sms_text,
                    "sent": sms_result.get("success", False),
                    "error": sms_result.get("error") if not sms_result.get("success") else None,
                    "created_at": now_iso,
                }
            )

    except Exception as e:
        logger.warning(f"IDV notification error for {user_id}: {e}")
