"""Central Email Notification Service — Sends, logs, and tracks all emails via Resend.

Usage:
    from utils.email_notifications import notify
    await notify.welcome(user_id, email, name)
    await notify.login_alert(user_id, email, name, ip, location, device)
"""

import os
import uuid
import hashlib
import logging
from datetime import datetime, timezone

from utils.email_service import send_email, is_email_configured
from utils.email_template_policy import is_protected_subject_override_target
from utils.email_templates import (
    build_welcome_email,
    build_account_verification_email,
    build_password_reset_email,
    build_security_alert_email,
    build_subscription_confirmation_email,
    build_support_ticket_email,
    build_weekly_digest_email,
)

logger = logging.getLogger(__name__)

BRAND_NAME = os.environ.get("BRAND_NAME", "RealAICoach")
FRONTEND_URL = os.environ.get("FRONTEND_BASE_URL", "")


async def _get_db():
    from routes.db import db

    return db


async def _check_preference(user_id: str, email_type: str) -> bool:
    """Check if user has opted in for this email type. Returns True if allowed."""
    db = await _get_db()
    prefs = await db.email_preferences.find_one({"user_id": user_id}, {"_id": 0})
    if not prefs:
        return True  # Default: all emails enabled
    # Check the specific preference; default True if not set
    return prefs.get(email_type, True)


async def _log_email(
    user_id: str,
    email: str,
    email_type: str,
    subject: str,
    status: str,
    message_id: str = "",
    error: str = "",
) -> str:
    """Log email send attempt to DB for tracking."""
    db = await _get_db()
    log_id = f"elog_{uuid.uuid4().hex[:12]}"
    doc = {
        "log_id": log_id,
        "user_id": user_id,
        "email": email,
        "email_type": email_type,
        "subject": subject,
        "status": status,
        "message_id": message_id,
        "error": error,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_logs.insert_one(doc)
    return log_id


async def _send_and_log(
    user_id: str,
    email: str,
    email_type: str,
    subject: str,
    html: str,
    name: str = "",
    skip_pref_check: bool = False,
    dedupe_key: str | None = None,
) -> dict:
    """Core send+log function with open/click tracking. Returns result dict."""
    # ── A/B test integration: check for active test on this template type ──
    ab_send_id = None
    try:
        from routes.ab_testing import get_active_test_for_template, assign_variant
        ab_test = await get_active_test_for_template(email_type)
        if ab_test:
            assignment = await assign_variant(user_id, email_type, ab_test["test_id"])
            if assignment:
                variant = assignment["variant"]
                ab_send_id = assignment["send_id"]
                if variant.get("subject_line"):
                    subject = variant["subject_line"]
                # Inject A/B open-tracking pixel
                pixel = f'<img src="{FRONTEND_URL}/api/ab-testing/track/open/{ab_send_id}" width="1" height="1" style="display:none" alt="" />'
                html = html.replace("</body>", f"{pixel}</body>")
                # Inject A/B click tracking: wrap primary CTA links
                click_url = f"{FRONTEND_URL}/api/ab-testing/track/click/{ab_send_id}"
                import re as _re
                html = _re.sub(
                    r'href="([^"]*?/subscription/plans[^"]*?)"',
                    f'href="{click_url}"',
                    html,
                    count=1,
                )
                # Also replace auth/login links for click tracking
                html = _re.sub(
                    r'href="([^"]*?/auth/login[^"]*?)"',
                    f'href="{click_url}"',
                    html,
                    count=1,
                )
                # Replace CTA text if variant specifies one
                if variant.get("cta_text"):
                    cta = variant["cta_text"]
                    for pattern in [
                        r"(Get Started\s*&#8594;)",
                        r"(Upgrade Now\s*&#8594;)",
                        r"(View Details\s*&#8594;)",
                    ]:
                        html = _re.sub(pattern, f"{cta} &#8594;", html)
    except Exception as e:
        logger.warning(f"A/B test integration non-fatal: {e}")

    normalized_email_type = str(email_type or "").strip().lower()

    # Check for AI-optimized subject override
    try:
        db_conn = await _get_db()
        override = await db_conn.email_subject_overrides.find_one(
            {"email_type": email_type, "active": True}, {"_id": 0}
        )
        # Lock critical reminder semantics: never apply generic A/B subject overrides
        # to reminder-family templates, otherwise stale placeholder copy can blast
        # globally (e.g., hardcoded names from preview/sample content).
        if (
            override
            and override.get("optimized_subject")
            and not is_protected_subject_override_target(normalized_email_type)
        ):
            subject = override["optimized_subject"]
    except Exception:
        pass  # Non-fatal: use original subject

    # ── Auto-translate email to user's preferred language ──
    try:
        from services.auto_translate import get_user_language, translate_email_html

        user_lang = await get_user_language(user_id)
        if user_lang and user_lang != "en":
            subject, html = await translate_email_html(html, subject, user_lang)
            logger.info(f"Email translated to {user_lang} for user {user_id}")
    except Exception as e:
        logger.warning(f"Email translation failed (non-fatal): {e}")

    # Check preference unless skipped (transactional emails skip)
    if not skip_pref_check:
        if not await _check_preference(user_id, email_type):
            logger.info(f"Email {email_type} skipped for {user_id} (opted out)")
            return {"success": False, "skipped": True, "reason": "opted_out"}

    if not is_email_configured():
        await _log_email(user_id, email, email_type, subject, "failed", error="Email service not configured")
        return {"success": False, "error": "Email service not configured"}

    # Inject open/click tracking
    tracking_id = f"etrk_{uuid.uuid4().hex[:16]}"
    try:
        from routes.email_notifications import inject_tracking
        base_url = os.environ.get("FRONTEND_BASE_URL", "")
        html = inject_tracking(html, tracking_id, base_url)
    except Exception as e:
        logger.warning(f"Tracking injection failed (non-fatal): {e}")

    result = await send_email(
        recipient_email=email,
        subject=subject,
        content=html,
        recipient_name=name,
        template_key=email_type,
        dedupe_key=dedupe_key,
    )

    if result.get("skipped"):
        status = "skipped"
    else:
        status = "sent" if result.get("success") else "failed"
    msg_id = result.get("message_id", "")
    error = result.get("error", "")
    log_id = await _log_email(user_id, email, email_type, subject, status, msg_id, error)

    # Create analytics tracking record
    if status == "sent":
        try:
            db = await _get_db()
            await db.email_analytics.insert_one({
                "tracking_id": tracking_id,
                "log_id": log_id,
                "user_id": user_id,
                "email": email,
                "email_type": email_type,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "open_count": 0,
                "click_count": 0,
                "events": [],
            })
        except Exception as e:
            logger.warning(f"Analytics record creation failed (non-fatal): {e}")

    logger.info(f"Email [{email_type}] to {email}: {status} (log={log_id}, track={tracking_id})")

    # Update A/B test send record with email log reference
    if ab_send_id and status == "sent":
        try:
            db = await _get_db()
            await db.ab_test_sends.update_one(
                {"send_id": ab_send_id},
                {"$set": {"email_sent": True, "log_id": log_id}},
            )
        except Exception:
            pass

    return {**result, "log_id": log_id}


class EmailNotifier:
    """Convenient methods for each email notification type."""

    async def welcome(self, user_id: str, email: str, name: str) -> dict:
        tpl = build_welcome_email(
            name,
            [
                "Complete your profile",
                "Start your first coaching session",
                "Explore the resource library",
            ],
        )
        return await _send_and_log(user_id, email, "welcome", tpl.subject, tpl.html, name, skip_pref_check=True)

    async def account_verification(
        self, user_id: str, email: str, name: str, verify_link: str, expires_hours: int = 24
    ) -> dict:
        tpl = build_account_verification_email(name, verify_link, expires_hours)
        return await _send_and_log(
            user_id, email, "account_verification", tpl.subject, tpl.html, name, skip_pref_check=True
        )

    async def password_reset(self, user_id: str, email: str, reset_link: str, expires_min: int = 15) -> dict:
        tpl = build_password_reset_email(reset_link, expires_min)
        return await _send_and_log(user_id, email, "password_reset", tpl.subject, tpl.html, skip_pref_check=True)

    async def login_alert(self, user_id: str, email: str, name: str, ip: str, location: str, device: str) -> dict:
        time_str = datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
        tpl = build_security_alert_email(name, location, device, time_str)
        # Override subject for login alert specifically
        subject = f"New login to your {BRAND_NAME} account"
        dedupe_window_seconds = int(os.environ.get("LOGIN_ALERT_DEDUPE_WINDOW_SECONDS", "3600"))
        now_ts = int(datetime.now(timezone.utc).timestamp())
        dedupe_bucket = max(1, now_ts // max(60, dedupe_window_seconds))
        # Global anti-duplication policy for login alerts:
        # only one login alert per user/email per window bucket.
        fp_src = "|".join([
            str(user_id or "").strip().lower(),
            str(email or "").strip().lower(),
            "login_alert",
        ])
        fp = hashlib.sha256(fp_src.encode("utf-8", errors="ignore")).hexdigest()[:24]
        dedupe_key = f"login-alert:{fp}:{dedupe_bucket}"
        return await _send_and_log(user_id, email, "login_alert", subject, tpl.html, name, dedupe_key=dedupe_key)

    async def suspicious_login(self, user_id: str, email: str, name: str, ip: str, location: str, reason: str, device: str = "Unknown Device") -> dict:
        time_str = datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
        from utils.email_templates import build_suspicious_login_email

        tpl = build_suspicious_login_email(name, ip, location, reason, time_str, device)
        subject = f"Suspicious login attempt — {BRAND_NAME}"
        return await _send_and_log(user_id, email, "suspicious_login", subject, tpl.html, name, skip_pref_check=True)

    async def subscription_confirmation(
        self, user_id: str, email: str, name: str, plan: str, billing_cycle: str, renewal_date: str
    ) -> dict:
        tpl = build_subscription_confirmation_email(name, plan, billing_cycle, renewal_date)
        return await _send_and_log(
            user_id, email, "subscription_confirmation", tpl.subject, tpl.html, name, skip_pref_check=True
        )

    async def admin_approval(self, admin_email: str, admin_name: str, action: str, details: str) -> dict:
        from utils.email_templates import _wrap

        body_html = f"""
        <p style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Action Required: Admin Approval</p>
        <p style="margin:0 0 16px;">Hi {admin_name},</p>
        <p style="margin:0 0 16px;">A new item requires your review:</p>
        <div style="background:#F8FAFC;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:14px 18px;margin:18px 0;font-size:13px;color:#475569;line-height:1.7;">
          <strong>Action:</strong> {action}<br>
          <strong>Details:</strong> {details}
        </div>
        """
        subject = f"{BRAND_NAME} — Admin Approval: {action}"
        html = _wrap(subject, "Admin action required", body_html, "Review Now", f"{FRONTEND_URL}/admin")
        return await _send_and_log(
            "admin", admin_email, "admin_approval", subject, html, admin_name, skip_pref_check=True
        )

    async def ticket_response(
        self, user_id: str, email: str, name: str, ticket_id: str, subject_line: str, response_preview: str
    ) -> dict:
        tpl = build_support_ticket_email(name, ticket_id, subject_line, response_preview)
        return await _send_and_log(user_id, email, "ticket_response", tpl.subject, tpl.html, name)

    async def reminder(
        self,
        user_id: str,
        email: str,
        name: str,
        title: str,
        time_str: str,
        reminder_type: str = "booking",
        details: str = "",
    ) -> dict:
        from utils.email_templates import _wrap

        body_html = f"""
        <p style="color:#0F172A;font-size:16px;font-weight:600;margin:0 0 6px;">Reminder: {title}</p>
        <p style="margin:0 0 16px;">Hi {name},</p>
        <p style="margin:0 0 16px;">This is a friendly reminder about your upcoming event:</p>
        <div style="background:#F8FAFC;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:14px 18px;margin:18px 0;font-size:13px;color:#475569;line-height:1.7;">
          <strong>{title}</strong><br>
          <span style="color:#64748B;">When:</span> {time_str}<br>
          {"<span style='color:#64748B;'>Details:</span> " + details + "<br>" if details else ""}
        </div>
        """
        subject = f"Reminder: {title}"
        html = _wrap(subject, "Upcoming event reminder", body_html, "View Details", FRONTEND_URL)
        return await _send_and_log(user_id, email, "reminder", subject, html, name)

    async def weekly_engagement(self, user_id: str, email: str, name: str, highlights: list, stats: list) -> dict:
        tpl = build_weekly_digest_email(name, highlights, stats)
        return await _send_and_log(user_id, email, "weekly_engagement", tpl.subject, tpl.html, name)


# Singleton instance
notify = EmailNotifier()


async def send_fraud_alert_email(
    admin_email: str, user_email: str, risk_score: int, risk_level: str, signals: str, scan_time: str
) -> dict:
    """Send fraud alert email to an admin."""
    from utils.email_templates import build_fraud_alert_admin_email

    tpl = build_fraud_alert_admin_email(user_email, risk_score, risk_level, signals, scan_time)
    return await _send_and_log("admin", admin_email, "fraud_alert_admin", tpl.subject, tpl.html, skip_pref_check=True)


async def send_platform_employee_invitation(
    recipient_email: str,
    platform_role: str,
    invited_by_email: str,
    invite_url: str,
    expires_in_hours: int = 72,
) -> dict:
    """Send a platform-employee invitation email with a one-time acceptance link (72h expiry).

    The email always displays the branded sender identity `careers@realaicoach.app` to
    recipients (not the specific admin's email). The real admin identity is preserved in
    the audit log at the call site via `_log_audit()`.
    """
    from utils.email_templates import _wrap

    # Branded sender identity for all candidate-facing platform invitations.
    # Single source of truth — env-configurable so rebranding doesn't require a code deploy.
    BRANDED_INVITER = os.environ.get("PLATFORM_INVITE_BRAND_SENDER", "careers@realaicoach.app")

    subject = f"[{BRAND_NAME}] You've been invited as {platform_role}"
    body_html = f"""
    <p style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 6px;">You're invited to join {BRAND_NAME}</p>
    <p style="margin:0 0 14px;color:#475569;font-size:14px;line-height:1.6;">
      <strong>{BRANDED_INVITER}</strong> has invited you to become a platform employee with the role of
      <strong>{platform_role}</strong>. Click the button below to create your account — it takes less than a minute.
    </p>
    <div style="background:#EFF6FF;border-left:4px solid #2563EB;border-radius:0 10px 10px 0;padding:14px 18px;margin:14px 0;color:#1E3A8A;font-size:13px;line-height:1.7;">
      <strong>Role:</strong> {platform_role}<br>
      <strong>Expires:</strong> {expires_in_hours} hours from now<br>
      <strong>Invited by:</strong> {BRANDED_INVITER}
    </div>
    <p style="color:#64748B;font-size:12px;line-height:1.6;margin:14px 0 0;">
      If you didn't expect this invitation, you can ignore this email — no account will be created.
    </p>
    """
    html = _wrap(subject, f"Invitation expires in {expires_in_hours}h", body_html, "Accept invitation", invite_url)
    return await _send_and_log(
        "employee_invite", recipient_email, "platform_employee_invitation", subject, html, skip_pref_check=True
    )


async def send_theme_audit_regression_alert(
    admin_email: str,
    current_grade: str,
    current_fails: int,
    previous_grade: str,
    previous_fails: int,
    reason: str,
    trigger: str,
    top_failing_files: list | None = None,
) -> dict:
    """Send a regression alert when the nightly Theme Visibility Audit detects a drop in grade or
    an increase in FAIL count. Non-fatal — returns {success: bool, ...}.
    """
    from utils.email_templates import _wrap

    severity = "HIGH" if current_grade in ("C", "D", "F") or current_fails >= 5 else "MEDIUM"
    severity_color = "#DC2626" if severity == "HIGH" else "#D97706"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    files_html = ""
    if top_failing_files:
        rows = "".join(
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid #E2E8F0;font-family:monospace;font-size:12px;color:#0F172A;'>{(f.get('file') or '')[:80]}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #E2E8F0;text-align:right;color:#DC2626;font-weight:700;font-size:12px;'>{int(f.get('fail_count') or 0)}</td></tr>"
            for f in top_failing_files[:8]
        )
        files_html = f"""
        <p style="color:#334155;font-size:13px;font-weight:600;margin:20px 0 8px;">Top failing files</p>
        <table style="width:100%;border-collapse:collapse;border:1px solid #E2E8F0;border-radius:8px;overflow:hidden;margin:0 0 16px;">
          <thead>
            <tr style="background:#F8FAFC;">
              <th style="padding:8px 10px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:#64748B;">File</th>
              <th style="padding:8px 10px;text-align:right;font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:#64748B;">FAILs</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        """

    body_html = f"""
    <p style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 6px;">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{severity_color};vertical-align:middle;margin-right:8px;"></span>
      Theme Visibility Regression · {severity}
    </p>
    <p style="margin:0 0 16px;color:#475569;font-size:14px;line-height:1.6;">
      The scheduled <strong>{trigger}</strong> theme audit detected a regression in the platform's dark/light adaptive styling.
    </p>

    <div style="background:#FEF2F2;border-left:4px solid {severity_color};border-radius:0 10px 10px 0;padding:16px 20px;margin:18px 0;font-size:13px;color:#7F1D1D;line-height:1.8;">
      <strong>Reason:</strong> {reason or "Grade drop / FAIL increase"}<br>
      <strong>Current:</strong> Grade {current_grade} · {current_fails} FAIL{"s" if current_fails != 1 else ""}<br>
      <strong>Previous:</strong> Grade {previous_grade or "—"} · {previous_fails if previous_fails is not None else "—"} FAIL{"s" if previous_fails != 1 else ""}<br>
      <strong>Detected at:</strong> {now_str}
    </div>

    {files_html}

    <p style="color:#475569;font-size:13px;line-height:1.6;margin:18px 0 8px;">
      Open the Admin Console → Operations → <strong>Theme Audit</strong> to review per-file issues and click
      <em>Run Audit Now</em> after applying fixes to confirm a clean re-scan.
    </p>
    """

    subject = f"[{BRAND_NAME}] Theme regression — Grade {current_grade}, {current_fails} FAIL{'s' if current_fails != 1 else ''}"
    cta_url = f"{FRONTEND_URL}/admin-console?cat=operations&tab=theme-audit" if FRONTEND_URL else "#"
    html = _wrap(subject, "Automated platform health alert", body_html, "Open Theme Audit", cta_url)
    return await _send_and_log(
        "admin", admin_email, "theme_audit_regression", subject, html, skip_pref_check=True
    )
