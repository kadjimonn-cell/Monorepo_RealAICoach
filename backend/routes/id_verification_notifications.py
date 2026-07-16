"""ID verification notification helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from .db import db


async def send_idv_status_email(*, user_id: str, status: str, ai_result: dict, kyc: dict, logger, build_idv_approved_email, build_idv_rejected_email, build_idv_pending_review_email, build_idv_more_info_needed_email):
    try:
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
        if not user or not user.get("email"):
            return
        user_name = user.get("name", "User")
        user_email = user["email"]
        phone = kyc.get("phone", "")
        checks = ai_result.get("checks", [])
        confidence = float(ai_result.get("confidence_score") or 0)
        flags = ai_result.get("flags", [])
        now_iso = datetime.now(timezone.utc).isoformat()

        prefs = await db.idv_notification_prefs.find_one({"user_id": user_id}, {"_id": 0})
        email_enabled = prefs.get("email", True) if prefs else True
        sms_enabled = prefs.get("sms", True) if prefs else True

        tpl = None
        sms_text = ""
        retry_date = kyc.get("retry_available_date", "N/A")
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
            if retry_date != "N/A":
                try:
                    retry_date = datetime.fromisoformat(retry_date).strftime("%B %d, %Y")
                except (ValueError, TypeError):
                    pass
            tpl = build_idv_rejected_email(user_name=user_name, reasons=flags or ["Further review required"], flags=flags, retry_date=retry_date)
            sms_text = f"RealAICoach: Your ID Checker was declined. You may retry after {retry_date}. Check your email for details."
        elif status == "pending_review":
            tpl = build_idv_pending_review_email(user_name=user_name, ai_confidence=confidence, flags=flags if flags else None)
            sms_text = "RealAICoach: Your ID Checker is under review. Estimated: 1-2 business days. We'll notify you of the result."
        elif status == "more_info_needed":
            notes = "; ".join(flags) if flags else (kyc.get("admin_reason") or "Please provide additional details for your verification.")
            tpl = build_idv_more_info_needed_email(user_name=user_name, notes=notes)
            sms_text = "RealAICoach: More information is needed to complete your ID Checker. Please check your email for next steps."
        else:
            return

        email_result = {"success": False, "error": "disabled"}
        if email_enabled and tpl:
            from utils.email_service import send_catalog_template

            idv_template_map = {"verified": "idv_approved", "rejected": "idv_rejected", "pending_review": "idv_pending", "more_info_needed": "idv_more_info_needed"}
            tpl_key = idv_template_map.get(status)
            if tpl_key:
                idv_kwargs = {"user_name": user_name}
                if status == "verified":
                    idv_kwargs.update(tier=kyc.get("tier", "level_1"), checks_passed=sum(1 for c in checks if c.get("passed")), total_checks=len(checks), confidence=confidence)
                elif status == "rejected":
                    idv_kwargs.update(reasons=flags or ["Further review required"], flags=flags, retry_date=retry_date)
                elif status == "pending_review":
                    idv_kwargs.update(ai_confidence=confidence, flags=flags if flags else None)
                elif status == "more_info_needed":
                    idv_kwargs.update(notes="; ".join(flags) if flags else (kyc.get("admin_reason") or "Please provide additional details for your verification."))
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

        if status in {"verified", "rejected"}:
            try:
                from utils.email_service import send_catalog_template

                admin_tpl_key = "idv_admin_approved" if status == "verified" else "idv_admin_rejected"
                admin_users = await db.users.find({"$or": [{"is_admin": True}, {"role": "admin"}]}, {"_id": 0, "email": 1, "name": 1}).to_list(200)
                seen = set()
                admin_sent = 0
                for admin_user in admin_users:
                    admin_email = str(admin_user.get("email") or "").strip().lower()
                    if not admin_email or admin_email in seen:
                        continue
                    seen.add(admin_email)
                    payload = {
                        "recipient_name": admin_user.get("name") or "Admin",
                        "user_name": user_name,
                        "user_email": user_email,
                        "user_id": user_id,
                        "reviewed_by": kyc.get("admin_reviewed_by") or "system",
                    }
                    if status == "verified":
                        payload["confidence"] = confidence
                    else:
                        payload["reasons"] = flags or [kyc.get("rejection_reason") or "Further review required"]
                    admin_result = await send_catalog_template(recipient_email=admin_email, template_key=admin_tpl_key, **payload)
                    await db.idv_admin_email_log.insert_one(
                        {
                            "user_id": user_id,
                            "channel": "email",
                            "status": status,
                            "admin_email": admin_email,
                            "template": admin_tpl_key,
                            "sent": bool(admin_result.get("success")),
                            "error": admin_result.get("error") if not admin_result.get("success") else None,
                            "created_at": now_iso,
                        }
                    )
                    if admin_result.get("success"):
                        admin_sent += 1
                logger.info(f"IDV admin {status} emails sent: {admin_sent}")
            except Exception as admin_exc:
                logger.warning(f"Failed sending IDV admin decision emails: {admin_exc}")

        sms_result = {"success": False, "error": "disabled"}
        if sms_enabled and phone and sms_text:
            sms_result = {"success": False, "error": "SMS has been removed from this platform"}
            if sms_result.get("success"):
                logger.info(f"IDV SMS sent to {phone}: {status}")
            else:
                logger.warning(f"IDV SMS failed for {phone}: {sms_result.get('error')}")
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
    except Exception as exc:
        logger.warning(f"IDV notification error for {user_id}: {exc}")