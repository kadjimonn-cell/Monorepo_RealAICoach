"""Contact form — public endpoint for website visitors to send inquiries."""
import os
import logging
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request
import re
from typing import Literal

from routes.db import db, require_admin
from services.ai_helpers import ai_generate
from utils.email_service import send_catalog_template
from utils.field_encryption import encrypt_field, hash_lookup, decrypt_doc

logger = logging.getLogger("contact")
router = APIRouter(prefix="/contact", tags=["Contact"])

TEAM_EMAIL = os.environ.get("CONTACT_FORM_EMAIL", "support@realaicoach.app")

# Fields encrypted at rest on `contact_submissions` — admin reads must decrypt.
_CONTACT_ENC_FIELDS = ("name", "email", "company", "message", "ip")


class ContactFormRequest(BaseModel):
    name: str
    email: str
    subject: str = ""
    message: str
    context: str = ""
    intent: Literal["sales", "support", "partnerships", "press"] = "support"
    company: str | None = None
    team_size: str | None = None
    use_case: str | None = None
    priority: str | None = None
    timeline: str | None = None
    budget_range: str | None = None
    website: str | None = None
    region: str | None = None
    source: str | None = None


@router.post("/submit")
async def submit_contact_form(body: ContactFormRequest, request: Request):
    """Receive a contact form submission, store it, email the team, and send confirmation to user."""
    if not body.name.strip() or not body.email.strip() or not body.message.strip():
        raise HTTPException(status_code=400, detail="Name, email, and message are required")

    name_plain = body.name.strip()
    email_plain = body.email.strip()
    intent = str(body.intent or "support").strip().lower()
    subject_fallback_map = {
        "sales": "Sales Inquiry",
        "support": "Support Request",
        "partnerships": "Partnership Inquiry",
        "press": "Press Inquiry",
    }
    subject_plain = body.subject.strip() or subject_fallback_map.get(intent, "General Inquiry")
    message_plain = body.message.strip()
    company_plain = str(body.company or "").strip()
    ip_plain = request.client.host if request.client else None

    entry = {
        "submission_id": f"contact_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{abs(hash(email_plain.lower())) % 100000}",
        "name": encrypt_field(name_plain),
        "email": encrypt_field(email_plain),
        "email_hash": hash_lookup(email_plain),
        "subject": subject_plain,
        "intent": intent,
        "company": encrypt_field(company_plain) if company_plain else None,
        "team_size": str(body.team_size or "").strip(),
        "use_case": str(body.use_case or "").strip(),
        "timeline": str(body.timeline or "").strip(),
        "budget_range": str(body.budget_range or "").strip(),
        "website": str(body.website or "").strip(),
        "region": str(body.region or "").strip(),
        "source": str(body.source or "contact_page").strip() or "contact_page",
        "message": encrypt_field(message_plain),
        "context": body.context.strip(),
        "priority": str(body.priority or ("high" if body.context.strip() == "login-lockout" else "normal")).strip(),
        "tags": ["lockout_support"] if body.context.strip() == "login-lockout" else [],
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ip": encrypt_field(ip_plain) if ip_plain else None,
    }
    await db.contact_submissions.insert_one(entry)

    # --- Email to team ---
    f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;border-radius:16px;overflow:hidden;">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#10B981 0%,#06B6D4 25%,#3B82F6 50%,#8B5CF6 75%,#EC4899 100%);padding:28px 28px;text-align:center;">
        <h2 style="margin:0;color:#FFFFFF;font-size:22px;font-weight:900;text-shadow:0 1px 4px rgba(0,0,0,0.15);">📩 New Contact Form Submission</h2>
      </div>

      <!-- Body -->
      <div style="padding:28px;background:#FFFFFF;">

        <!-- Contact Details Table -->
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="color:#FFFFFF;font-size:12px;font-weight:800;padding:10px 14px;background:linear-gradient(135deg,#10B981,#059669);border-radius:8px;width:80px;vertical-align:middle;">Name</td>
            <td style="color:#0F172A;padding:10px 14px;font-size:15px;font-weight:700;">{body.name}</td>
          </tr>
          <tr><td colspan="2" style="padding:4px;"></td></tr>
          <tr>
            <td style="color:#FFFFFF;font-size:12px;font-weight:800;padding:10px 14px;background:linear-gradient(135deg,#3B82F6,#2563EB);border-radius:8px;vertical-align:middle;">Email</td>
            <td style="color:#0D9488;padding:10px 14px;font-size:15px;font-weight:700;">{body.email}</td>
          </tr>
          <tr><td colspan="2" style="padding:4px;"></td></tr>
          <tr>
            <td style="color:#FFFFFF;font-size:12px;font-weight:800;padding:10px 14px;background:linear-gradient(135deg,#8B5CF6,#7C3AED);border-radius:8px;vertical-align:middle;">Subject</td>
            <td style="color:#0F172A;padding:10px 14px;font-size:15px;font-weight:600;">{body.subject or 'General Inquiry'}</td>
          </tr>
          {"<tr><td colspan='2' style='padding:4px;'></td></tr><tr><td style='color:#FFFFFF;font-size:12px;font-weight:800;padding:10px 14px;background:linear-gradient(135deg,#F59E0B,#D97706);border-radius:8px;vertical-align:middle;'>Category</td><td style='color:#0F172A;padding:10px 14px;font-size:15px;font-weight:600;'>" + body.context + "</td></tr>" if body.context else ""}
        </table>

        <!-- Rainbow Divider -->
        <div style="height:3px;background:linear-gradient(90deg,#10B981,#3B82F6,#8B5CF6,#F59E0B);border-radius:2px;margin:20px 0;"></div>

        <!-- Message Box -->
        <div style="padding:20px;background:linear-gradient(135deg,#F0FDFA,#F0F9FF);border-radius:12px;border:2px solid #14B8A6;">
          <p style="color:#0D9488;font-size:12px;margin:0 0 10px;text-transform:uppercase;font-weight:800;letter-spacing:1px;">💬 MESSAGE</p>
          <p style="color:#1E293B;font-size:15px;line-height:1.7;margin:0;white-space:pre-wrap;">{body.message}</p>
        </div>

        <p style="color:#64748B;font-size:12px;margin-top:20px;font-weight:500;">Reply directly to this email to respond to the sender.</p>
      </div>
    </div>
    """

    team_result = await send_catalog_template(
        recipient_email=TEAM_EMAIL,
        template_key="contact_team_notify",
        sender_name=body.name,
        sender_email=body.email,
        subject=body.subject or "General Inquiry",
        message=body.message,
        category=body.context or "",
    )

    # --- Confirmation email to user ---
    base_url = os.environ.get("FRONTEND_BASE_URL", "https://realaicoach.app")
    signup_url = f"{base_url}/auth/register"
    first_name = body.name.strip().split()[0]

    f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:linear-gradient(180deg,#ECFDF5 0%,#EFF6FF 30%,#F5F3FF 60%,#FEF3C7 100%);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">

    <div style="background:#FFFFFF;border-radius:24px;overflow:hidden;border:2px solid transparent;box-shadow:0 8px 40px rgba(16,185,129,0.12),0 2px 8px rgba(59,130,246,0.08);">

      <!-- Brand Bar — bold multi-color gradient -->
      <div style="background:linear-gradient(135deg,#10B981 0%,#06B6D4 25%,#3B82F6 50%,#8B5CF6 75%,#EC4899 100%);padding:36px 32px;text-align:center;">
        <h1 style="margin:0;color:#FFFFFF;font-size:30px;font-weight:900;letter-spacing:-0.5px;text-shadow:0 2px 8px rgba(0,0,0,0.15);">RealAICoach</h1>
        <p style="margin:10px 0 0;color:#FFFFFF;font-size:14px;font-weight:600;letter-spacing:0.5px;">YOUR AI-POWERED GROWTH PARTNER</p>
      </div>

      <!-- Content -->
      <div style="padding:36px 32px 28px;">

        <h2 style="color:#0F172A;font-size:26px;font-weight:900;margin:0 0 6px;letter-spacing:-0.3px;">Thank you, {first_name}! 🎉</h2>
        <p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 28px;">We've received your message and our team is already on it!</p>

        <!-- Submission Summary — teal card -->
        <div style="border-radius:16px;overflow:hidden;margin-bottom:28px;border:2px solid #14B8A6;">
          <div style="padding:16px 20px;background:linear-gradient(135deg,#0D9488 0%,#0891B2 50%,#0EA5E9 100%);">
            <span style="color:#FFFFFF;font-size:13px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;">📋 YOUR SUBMISSION</span>
          </div>
          <div style="padding:20px;background:linear-gradient(180deg,#F0FDFA,#FFFFFF);">
            <table style="width:100%;border-collapse:collapse;">
              <tr>
                <td style="color:#FFFFFF;font-size:12px;font-weight:800;padding:10px 12px;width:80px;vertical-align:top;background:#0D9488;border-radius:8px;">Subject</td>
                <td style="color:#0F172A;font-size:15px;padding:10px 12px;font-weight:700;">{body.subject or 'General Inquiry'}</td>
              </tr>
              <tr><td colspan="2" style="padding:4px;"></td></tr>
              <tr>
                <td style="color:#FFFFFF;font-size:12px;font-weight:800;padding:10px 12px;vertical-align:top;background:#0891B2;border-radius:8px;">Message</td>
                <td style="color:#334155;font-size:14px;padding:10px 12px;line-height:1.6;">{body.message[:300]}{'...' if len(body.message) > 300 else ''}</td>
              </tr>
            </table>
          </div>
        </div>

        <!-- What to Expect — each step in a colored card -->
        <h3 style="color:#0F172A;font-size:20px;font-weight:900;margin:0 0 18px;">⚡ What happens next?</h3>

        <!-- Step 1 — Green -->
        <div style="background:linear-gradient(135deg,#ECFDF5,#D1FAE5);border-radius:14px;padding:18px 20px;margin-bottom:12px;border-left:4px solid #10B981;border:1px solid #A7F3D0;">
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="width:48px;vertical-align:top;">
                <div style="width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#10B981,#059669);text-align:center;line-height:40px;color:#FFFFFF;font-size:18px;font-weight:900;box-shadow:0 4px 12px rgba(16,185,129,0.4);">1</div>
              </td>
              <td style="padding-left:14px;">
                <p style="color:#065F46;font-size:16px;font-weight:800;margin:0;">Ticket Created</p>
                <p style="color:#047857;font-size:13px;margin:4px 0 0;line-height:1.5;">Your inquiry has been logged and assigned to the right team member.</p>
              </td>
            </tr>
          </table>
        </div>

        <!-- Step 2 — Blue -->
        <div style="background:linear-gradient(135deg,#EFF6FF,#DBEAFE);border-radius:14px;padding:18px 20px;margin-bottom:12px;border-left:4px solid #3B82F6;border:1px solid #93C5FD;">
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="width:48px;vertical-align:top;">
                <div style="width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#3B82F6,#2563EB);text-align:center;line-height:40px;color:#FFFFFF;font-size:18px;font-weight:900;box-shadow:0 4px 12px rgba(59,130,246,0.4);">2</div>
              </td>
              <td style="padding-left:14px;">
                <p style="color:#1E3A8A;font-size:16px;font-weight:800;margin:0;">Review & Response</p>
                <p style="color:#1D4ED8;font-size:13px;margin:4px 0 0;line-height:1.5;">Our team will respond within <strong style="color:#059669;font-size:14px;">24 hours</strong> on business days.</p>
              </td>
            </tr>
          </table>
        </div>

        <!-- Step 3 — Purple -->
        <div style="background:linear-gradient(135deg,#F5F3FF,#EDE9FE);border-radius:14px;padding:18px 20px;margin-bottom:28px;border-left:4px solid #8B5CF6;border:1px solid #C4B5FD;">
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="width:48px;vertical-align:top;">
                <div style="width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#8B5CF6,#7C3AED);text-align:center;line-height:40px;color:#FFFFFF;font-size:18px;font-weight:900;box-shadow:0 4px 12px rgba(139,92,246,0.4);">3</div>
              </td>
              <td style="padding-left:14px;">
                <p style="color:#4C1D95;font-size:16px;font-weight:800;margin:0;">Resolution</p>
                <p style="color:#6D28D9;font-size:13px;margin:4px 0 0;line-height:1.5;">We'll work with you until fully resolved. <strong style="color:#7C3AED;font-size:14px;">98% resolution rate.</strong></p>
              </td>
            </tr>
          </table>
        </div>

        <!-- Rainbow Divider -->
        <div style="height:4px;background:linear-gradient(90deg,#EF4444,#F59E0B,#10B981,#0EA5E9,#8B5CF6,#EC4899);border-radius:2px;margin:0 0 28px;"></div>

        <!-- CTA Section — vibrant gradient card -->
        <div style="background:linear-gradient(135deg,#ECFDF5 0%,#DBEAFE 35%,#EDE9FE 65%,#FEF3C7 100%);border-radius:20px;padding:36px 24px;text-align:center;border:2px solid #A7F3D0;box-shadow:0 4px 20px rgba(16,185,129,0.1),0 4px 20px rgba(59,130,246,0.1);">
          <h3 style="color:#0F172A;font-size:22px;font-weight:900;margin:0 0 10px;">🚀 Explore RealAICoach</h3>
          <p style="color:#334155;font-size:15px;line-height:1.7;margin:0 0 28px;">Join thousands leveraging <strong style="color:#2563EB;">live AI-powered tools</strong> for coaching, productivity, and career growth — <strong style="color:#059669;">free to start</strong>.</p>

          <a href="{signup_url}" style="display:inline-block;background:linear-gradient(135deg,#10B981 0%,#0EA5E9 50%,#8B5CF6 100%);color:#FFFFFF;font-size:18px;font-weight:900;text-decoration:none;padding:18px 52px;border-radius:16px;letter-spacing:-0.2px;box-shadow:0 8px 28px rgba(16,185,129,0.35),0 4px 12px rgba(59,130,246,0.2);text-shadow:0 1px 4px rgba(0,0,0,0.1);">
            ✨ Create Your Free Account
          </a>

          <div style="margin-top:24px;">
            <span style="display:inline-block;background:linear-gradient(135deg,#10B981,#059669);color:#FFFFFF;font-size:12px;font-weight:800;padding:8px 18px;border-radius:24px;margin:4px;box-shadow:0 2px 8px rgba(16,185,129,0.3);">🤖 AI Writer Pro</span>
            <span style="display:inline-block;background:linear-gradient(135deg,#3B82F6,#2563EB);color:#FFFFFF;font-size:12px;font-weight:800;padding:8px 18px;border-radius:24px;margin:4px;box-shadow:0 2px 8px rgba(59,130,246,0.3);">💬 Smart Chatbot</span>
            <span style="display:inline-block;background:linear-gradient(135deg,#8B5CF6,#7C3AED);color:#FFFFFF;font-size:12px;font-weight:800;padding:8px 18px;border-radius:24px;margin:4px;box-shadow:0 2px 8px rgba(139,92,246,0.3);">🎯 Career Coach</span>
            <span style="display:inline-block;background:linear-gradient(135deg,#F59E0B,#D97706);color:#FFFFFF;font-size:12px;font-weight:800;padding:8px 18px;border-radius:24px;margin:4px;box-shadow:0 2px 8px rgba(245,158,11,0.3);">💰 Financial Hub</span>
          </div>
        </div>
      </div>

      <!-- Footer — gradient -->
      <div style="background:linear-gradient(135deg,#F0FDFA,#EFF6FF,#F5F3FF);padding:24px 32px;text-align:center;border-top:2px solid #E2E8F0;">
        <p style="color:#475569;font-size:12px;font-weight:600;margin:0 0 4px;">RealAICoach &middot; 11501 Domain Dr, Suite 200, Austin, TX 78758</p>
        <p style="color:#64748B;font-size:11px;margin:0;">You received this because you contacted us via our website.</p>
      </div>
    </div>
  </div>
</body></html>"""

    user_result = await send_catalog_template(
        recipient_email=body.email.strip(),
        recipient_name=body.name.strip(),
        template_key="contact_form_confirmation",
        user_name=first_name,
        ticket_id=entry["submission_id"],
        subject_line=body.subject or "General Inquiry",
    )

    logger.info(f"Contact form: name={body.name}, email={body.email}, team_email={team_result.get('success')}, user_confirmation={user_result.get('success')}")

    return {
        "success": True,
        "reference_id": entry["submission_id"],
        "message": "Your message has been sent. We'll get back to you soon.",
        "email_delivered": team_result.get("success", False),
        "confirmation_sent": user_result.get("success", False),
        "intent": intent,
        "sla_hours": 4 if intent == "support" else 24,
    }


@router.post("")
@router.post("/")
async def submit_contact_form_alias(body: ContactFormRequest, request: Request):
    """Compatibility alias for legacy /api/contact POST clients."""
    return await submit_contact_form(body, request)


@router.get("")
@router.get("/")
async def contact_endpoint_info():
    """Compatibility info endpoint for legacy /api/contact GET checks."""
    return {
        "ok": True,
        "submit_endpoint": "/api/contact/submit",
        "method": "POST",
        "message": "Use POST /api/contact/submit to send contact requests.",
    }



async def process_contact_followups():
    """Check for contact submissions older than 24h with status 'new' and send follow-up emails."""
    base_url = os.environ.get("FRONTEND_BASE_URL", "https://realaicoach.app")
    signup_url = f"{base_url}/auth/register"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    pending = await db.contact_submissions.find({
        "status": "new",
        "followed_up": {"$ne": True},
        "created_at": {"$lt": cutoff},
    }).to_list(50)

    sent = 0
    for entry in pending:
        decrypt_doc(entry, _CONTACT_ENC_FIELDS)
        email_addr = entry.get("email", "").strip()
        name = entry.get("name", "").strip()
        subject = entry.get("subject", "General Inquiry")
        first_name = name.split()[0] if name else "there"

        if not email_addr:
            continue

        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#080E1A;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
    <div style="background:linear-gradient(145deg,#0F172A 0%,#1E293B 100%);border-radius:20px;overflow:hidden;border:1px solid #1E3A5F;">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#3B82F6 0%,#8B5CF6 100%);padding:28px 32px;text-align:center;">
        <h1 style="margin:0;color:#FFF;font-size:22px;font-weight:800;">We haven't forgotten about you</h1>
        <p style="margin:8px 0 0;color:#E2E8F0;font-size:14px;">Your inquiry is being prioritized</p>
      </div>

      <!-- Body -->
      <div style="padding:32px;">
        <p style="color:#F8FAFC;font-size:16px;font-weight:600;margin:0 0 12px;">Hi {first_name},</p>
        <p style="color:#94A3B8;font-size:14px;line-height:1.7;margin:0 0 24px;">
          We wanted to let you know that your message about <strong style="color:#E2E8F0;">"{subject}"</strong> is still in our queue and being actively reviewed by our team. We understand your time is valuable, and we're working to get you a thorough response.
        </p>

        <!-- Status Card -->
        <div style="background:#0B1120;border-radius:14px;padding:20px;border:1px solid #1E293B;margin-bottom:24px;">
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
            <tr>
              <td style="width:10px;height:10px;border-radius:50%;background:#F59E0B;vertical-align:middle;"></td>
              <td style="padding-left:10px;vertical-align:middle;"><span style="color:#F59E0B;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">In Review</span></td>
            </tr>
          </table>
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="color:#64748B;font-size:12px;padding:4px 0;width:80px;">Submitted</td>
              <td style="color:#CBD5E1;font-size:13px;padding:4px 0;">{entry.get('created_at', '')[:10]}</td>
            </tr>
            <tr>
              <td style="color:#64748B;font-size:12px;padding:4px 0;">Subject</td>
              <td style="color:#CBD5E1;font-size:13px;padding:4px 0;">{subject}</td>
            </tr>
            <tr>
              <td style="color:#64748B;font-size:12px;padding:4px 0;">Priority</td>
              <td style="color:#10B981;font-size:13px;padding:4px 0;font-weight:600;">Elevated</td>
            </tr>
          </table>
        </div>

        <p style="color:#94A3B8;font-size:14px;line-height:1.7;margin:0 0 28px;">
          Our support team will reach out to you shortly. In the meantime, you can explore everything RealAICoach has to offer:
        </p>

        <!-- CTA -->
        <div style="text-align:center;margin-bottom:24px;">
          <a href="{signup_url}" style="display:inline-block;background:linear-gradient(135deg,#3B82F6 0%,#8B5CF6 100%);color:#FFF;font-size:15px;font-weight:800;text-decoration:none;padding:14px 36px;border-radius:12px;">
            Explore RealAICoach Free
          </a>
        </div>

        <p style="color:#64748B;font-size:13px;line-height:1.6;margin:0;text-align:center;">
          Need urgent help? Reply directly to this email and we'll fast-track your request.
        </p>
      </div>

      <!-- Footer -->
      <div style="background:#080E1A;padding:20px 32px;text-align:center;border-top:1px solid #1E293B;">
        <p style="color:#475569;font-size:12px;margin:0 0 4px;">RealAICoach &middot; 11501 Domain Dr, Suite 200, Austin, TX 78758</p>
        <p style="color:#334155;font-size:11px;margin:0;">This is an automated follow-up. A team member will respond personally.</p>
      </div>
    </div>
  </div>
</body></html>"""

        result = await send_catalog_template(
            recipient_email=email_addr,
            template_key="contact_followup",
            recipient_name=name,
            user_name=name,
            subject=subject,
            submitted_date=entry.get('created_at', '')[:10],
            priority="Elevated",
            signup_url=signup_url,
        )

        if result.get("success") or result.get("id"):
            await db.contact_submissions.update_one(
                {"_id": entry["_id"]},
                {"$set": {"followed_up": True, "followed_up_at": datetime.now(timezone.utc).isoformat()}}
            )
            sent += 1
            logger.info(f"Follow-up sent to {email_addr} for submission from {entry.get('created_at')}")

    return {"sent": sent, "checked": len(pending)}


@router.post("/followup/trigger")
async def trigger_followup(req: Request):
    """Admin endpoint to manually trigger the follow-up check."""
    await require_admin(req)
    result = await process_contact_followups()
    return {"success": True, **result}


@router.get("/followup/stats")
async def followup_stats(req: Request):
    """Get stats about contact submissions and follow-ups."""
    await require_admin(req)
    total = await db.contact_submissions.count_documents({})
    new_count = await db.contact_submissions.count_documents({"status": "new"})
    followed_up = await db.contact_submissions.count_documents({"followed_up": True})
    pending_followup = await db.contact_submissions.count_documents({
        "status": "new",
        "followed_up": {"$ne": True},
        "created_at": {"$lt": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()},
    })
    return {
        "total": total,
        "new": new_count,
        "followed_up": followed_up,
        "pending_followup": pending_followup,
    }



@router.get("/analytics")
async def contact_analytics(req: Request, days: int = 30):
    """Compute contact submission analytics for the admin dashboard."""
    await require_admin(req)
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()

    # All submissions in the period
    all_subs = await db.contact_submissions.find(
        {"created_at": {"$gte": cutoff}}, {"_id": 0}
    ).to_list(5000)
    for s in all_subs:
        decrypt_doc(s, _CONTACT_ENC_FIELDS)

    total = len(all_subs)
    responded = [s for s in all_subs if s.get("responded_at")]
    [s for s in all_subs if s.get("status") == "closed"]

    # Response times (hours)
    response_times = []
    for s in responded:
        try:
            created = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            resp_at = datetime.fromisoformat(s["responded_at"].replace("Z", "+00:00"))
            diff_hrs = (resp_at - created).total_seconds() / 3600
            if diff_hrs >= 0:
                response_times.append(diff_hrs)
        except Exception:
            pass

    avg_response_hrs = round(sum(response_times) / len(response_times), 1) if response_times else None
    within_24h = sum(1 for t in response_times if t <= 24)
    sla_pct = round((within_24h / len(response_times)) * 100) if response_times else None

    # Daily volume for chart
    daily = {}
    for s in all_subs:
        day = s.get("created_at", "")[:10]
        daily[day] = daily.get(day, 0) + 1
    volume = [{"date": d, "count": c} for d, c in sorted(daily.items())]

    # Topic distribution
    topics = {}
    for s in all_subs:
        subj = s.get("subject") or "General Inquiry"
        topics[subj] = topics.get(subj, 0) + 1
    topic_dist = [{"topic": t, "count": c} for t, c in sorted(topics.items(), key=lambda x: -x[1])]

    # Overall totals from DB (not filtered by date)
    all_time_total = await db.contact_submissions.count_documents({})
    all_time_responded = await db.contact_submissions.count_documents({"status": "responded"})
    all_time_closed = await db.contact_submissions.count_documents({"status": "closed"})
    response_rate = round(((all_time_responded + all_time_closed) / all_time_total) * 100) if all_time_total else 0

    return {
        "period_days": days,
        "total_in_period": total,
        "responded_in_period": len(responded),
        "avg_response_hours": avg_response_hrs,
        "sla_24h_pct": sla_pct,
        "response_rate": response_rate,
        "daily_volume": volume,
        "topic_distribution": topic_dist,
        "all_time": {
            "total": all_time_total,
            "responded": all_time_responded,
            "closed": all_time_closed,
        },
    }


@router.get("/submissions")
async def list_submissions(req: Request, status: str = "all", search: str = "", limit: int = 50, skip: int = 0):
    """List contact submissions for admin panel."""
    await require_admin(req)
    query = {}
    if status and status != "all":
        query["status"] = status
    if search:
        # Encrypted fields (name, email) cannot be regex-searched.
        # Full email → email_hash exact match; everything else → subject regex.
        or_clauses = [
            {"subject": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]
        if "@" in str(search):
            or_clauses.append({"email_hash": hash_lookup(str(search))})
        query["$or"] = or_clauses

    cursor = db.contact_submissions.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    submissions = await cursor.to_list(limit)
    for s in submissions:
        decrypt_doc(s, _CONTACT_ENC_FIELDS)
    total = await db.contact_submissions.count_documents(query)

    # Enrich stats
    stats = {
        "total": await db.contact_submissions.count_documents({}),
        "new": await db.contact_submissions.count_documents({"status": "new"}),
        "in_review": await db.contact_submissions.count_documents({"status": "in_review"}),
        "responded": await db.contact_submissions.count_documents({"status": "responded"}),
        "closed": await db.contact_submissions.count_documents({"status": "closed"}),
        "followed_up": await db.contact_submissions.count_documents({"followed_up": True}),
        "lockout_support": await db.contact_submissions.count_documents({"$or": [{"context": "login-lockout"}, {"tags": "lockout_support"}, {"priority": "high"}]}),
    }

    return {"success": True, "submissions": submissions, "total": total, "stats": stats}


class UpdateSubmissionRequest(BaseModel):
    status: str = ""
    admin_notes: str = ""


class ReplyRequest(BaseModel):
    message: str
    subject: str = ""


class SuggestReplyRequest(BaseModel):
    tone: str = "professional"


@router.put("/submissions/{submission_id}/status")
async def update_submission_status(submission_id: str, body: UpdateSubmissionRequest, req: Request):
    """Update submission status and admin notes."""
    admin = await require_admin(req)
    update = {}
    if body.status:
        update["status"] = body.status
    if body.admin_notes is not None:
        update["admin_notes"] = body.admin_notes
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = admin.user_id

    result = await db.contact_submissions.update_one(
        {"submission_id": submission_id, "status": {"$ne": "closed"}},
        {"$set": update},
    )
    if result.modified_count == 0:
        return {"success": False, "message": "Submission not found or already closed."}

    return {"success": True, "message": f"Status updated to {body.status}."}


@router.post("/submissions/{submission_id}/reply")
async def reply_to_submission(submission_id: str, body: ReplyRequest, req: Request):
    """Send a reply email to the contact submission author."""
    admin = await require_admin(req)
    submission = await db.contact_submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    decrypt_doc(submission, _CONTACT_ENC_FIELDS)

    first_name = submission.get("name", "there").split()[0]
    base_url = os.environ.get("FRONTEND_BASE_URL", "https://realaicoach.app")
    signup_url = f"{base_url}/auth/register"

    f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#080E1A;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
    <div style="background:linear-gradient(145deg,#0F172A 0%,#1E293B 100%);border-radius:20px;overflow:hidden;border:1px solid #1E3A5F;">

      <div style="background:linear-gradient(135deg,#00D4AA 0%,#00B4D8 50%,#3B82F6 100%);padding:24px 32px;">
        <h1 style="margin:0;color:#0F172A;font-size:20px;font-weight:800;">RealAICoach Support</h1>
        <p style="margin:4px 0 0;color:#0D1426;font-size:13px;">Response to your inquiry</p>
      </div>

      <div style="padding:32px;">
        <p style="color:#F8FAFC;font-size:16px;font-weight:600;margin:0 0 8px;">Hi {first_name},</p>
        <p style="color:#94A3B8;font-size:13px;margin:0 0 20px;">Regarding your inquiry about: <strong style="color:#E2E8F0;">{submission.get('subject', 'General Inquiry')}</strong></p>

        <div style="background:#0B1120;border-radius:14px;padding:20px;border:1px solid #1E293B;border-left:3px solid #00D4AA;margin-bottom:24px;">
          <p style="color:#F1F5F9;font-size:14px;line-height:1.7;margin:0;white-space:pre-wrap;">{body.message}</p>
        </div>

        <div style="height:1px;background:linear-gradient(90deg,transparent,#334155,transparent);margin:24px 0;"></div>

        <div style="text-align:center;padding:20px 0;">
          <p style="color:#94A3B8;font-size:13px;margin:0 0 16px;">Haven't signed up yet? Start using our AI-powered tools today:</p>
          <a href="{signup_url}" style="display:inline-block;background:linear-gradient(135deg,#00D4AA 0%,#00B4D8 100%);color:#0F172A;font-size:14px;font-weight:800;text-decoration:none;padding:12px 32px;border-radius:10px;">
            Get Started Free
          </a>
        </div>
      </div>

      <div style="background:#080E1A;padding:16px 32px;text-align:center;border-top:1px solid #1E293B;">
        <p style="color:#475569;font-size:11px;margin:0;">RealAICoach Support &middot; You can reply directly to this email.</p>
      </div>
    </div>
  </div>
</body></html>"""

    result = await send_catalog_template(
        recipient_email=submission.get("email", ""),
        template_key="contact_admin_reply",
        recipient_name=submission.get("name", ""),
        user_name=submission.get("name", "there"),
        original_subject=submission.get("subject", "General Inquiry"),
        reply_message=body.message,
        custom_subject=body.subject or "",
        signup_url=signup_url,
    )

    email_sent = result.get("success") or result.get("id")
    if email_sent:
        await db.contact_submissions.update_one(
            {"submission_id": submission_id},
            {"$set": {
                "status": "responded",
                "responded_at": datetime.now(timezone.utc).isoformat(),
                "admin_reply": body.message,
                "replied_by": admin.user_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

    return {"success": bool(email_sent), "message": "Reply sent." if email_sent else "Failed to send reply."}


@router.post("/submissions/{submission_id}/suggest-reply")
async def suggest_reply(submission_id: str, body: SuggestReplyRequest, req: Request):
    await require_admin(req)
    submission = await db.contact_submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    decrypt_doc(submission, _CONTACT_ENC_FIELDS)

    first_name = (submission.get("name") or "there").split()[0]
    fallback = (
        f"Hi {first_name},\n\n"
        f"Thank you for reaching out about \"{submission.get('subject', 'your request')}\". "
        "We’ve reviewed your message and our support team is actively looking into it. "
        "We’ll follow up shortly with the next steps.\n\n"
        "Best regards,\nRealAICoach Support"
    )
    try:
        suggestion = await ai_generate(
            "You are a senior enterprise support agent drafting concise, professional email replies. No markdown. 3 short paragraphs max.",
            (
                f"Tone: {(body.tone or 'professional').strip().lower()}\n"
                f"Customer name: {submission.get('name', '')}\n"
                f"Subject: {submission.get('subject', '')}\n"
                f"Priority: {submission.get('priority', '')}\n"
                f"Context: {submission.get('context', '')}\n"
                f"Message: {submission.get('message', '')}\n"
                "Draft a helpful reply that acknowledges the request, explains the next step, and sounds premium/supportive."
            ),
            f"contact-reply-{submission_id}",
        )
        suggestion = (suggestion or '').strip() or fallback
    except Exception:
        suggestion = fallback

    return {"success": True, "suggested_reply": suggestion}
