# ruff: noqa
"""Churn Recovery Service — Automated win-back emails for cancelled subscribers."""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from routes.db import db
from utils.email_service import render_email_logo

logger = logging.getLogger(__name__)

MAX_REMINDERS = 6  # Stop after 6 bi-weekly reminders (3 months)
REMINDER_INTERVAL_DAYS = 14
DISCOUNT_PERCENT = 10
DISCOUNT_VALIDITY_DAYS = 30


def _generate_discount_code() -> str:
    return f"COMEBACK{uuid.uuid4().hex[:6].upper()}"


def _build_cancellation_email_html(user_name: str, discount_code: str, discount_expiry: str) -> str:
    """Enterprise-grade cancellation confirmation email."""
    logo_html = render_email_logo(variant="default")
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#FFFFFF;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 16px;">
  <!-- Card -->
  <div style="border-radius:20px;overflow:hidden;border:1px solid #E2E8F0;background:#FFFFFF;">
    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1E293B 0%,#0F172A 100%);padding:40px 32px 32px;text-align:center;">
      {logo_html}
      <div style="width:72px;height:72px;border-radius:50%;background:#1C1012;border:2px solid #3D1B22;margin:20px auto 16px;text-align:center;">
        <span style="font-size:32px;line-height:72px;">&#128075;</span>
      </div>
      <h1 style="color:#0F172A;font-size:24px;font-weight:800;margin:0 0 8px;letter-spacing:-0.5px;">We're Sorry to See You Go</h1>
      <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">Your subscription has been cancelled successfully</p>
    </div>

    <!-- Body -->
    <div style="padding:32px;">
      <p style="color:#334155;font-size:15px;line-height:1.7;margin:0 0 20px;">Hi {user_name},</p>
      <p style="color:#475569;font-size:14px;line-height:1.7;margin:0 0 20px;">
        We truly appreciate the time you spent with RealAICoach. Your growth and success mean everything to us, and we hope our platform contributed positively to your journey.
      </p>
      <p style="color:#475569;font-size:14px;line-height:1.7;margin:0 0 24px;">
        We understand that needs change, and we respect your decision. But we'd love to have you back whenever you're ready.
      </p>

      <!-- Discount Offer -->
      <div style="background:linear-gradient(135deg,#059669 0%,#10B981 100%);border-radius:16px;padding:28px 24px;text-align:center;margin:0 0 24px;">
        <p style="color:rgba(255,255,255,0.9);font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin:0 0 8px;">EXCLUSIVE COMEBACK OFFER</p>
        <p style="color:#FFFFFF;font-size:36px;font-weight:900;margin:0 0 6px;letter-spacing:-1px;">{DISCOUNT_PERCENT}% OFF</p>
        <p style="color:rgba(255,255,255,0.85);font-size:13px;margin:0 0 16px;">on your next subscription</p>
        <div style="display:inline-block;background:rgba(0,0,0,0.25);border-radius:12px;padding:14px 28px;border:2px dashed rgba(255,255,255,0.3);">
          <p style="color:rgba(255,255,255,0.7);font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin:0 0 4px;">YOUR CODE</p>
          <p style="color:#FFFFFF;font-size:24px;font-weight:800;letter-spacing:4px;margin:0;">{discount_code}</p>
        </div>
        <p style="color:rgba(255,255,255,0.7);font-size:11px;margin:12px 0 0;">Valid until {discount_expiry}</p>
      </div>

      <!-- Steps -->
      <div style="background:#F8FAFC;border-radius:14px;padding:24px;border:1px solid #E2E8F0;margin:0 0 24px;">
        <p style="color:#0F172A;font-size:14px;font-weight:700;margin:0 0 16px;">How to reactivate:</p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:0 0 14px;">
              <table role="presentation" cellpadding="0" cellspacing="0"><tr>
                <td style="width:32px;height:32px;border-radius:8px;background:rgba(59,130,246,0.15);text-align:center;vertical-align:middle;"><span style="color:#3B82F6;font-size:14px;font-weight:800;line-height:32px;">1</span></td>
                <td style="padding-left:12px;"><p style="color:#334155;font-size:13px;margin:0;">Log in to your RealAICoach account</p></td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 0 14px;">
              <table role="presentation" cellpadding="0" cellspacing="0"><tr>
                <td style="width:32px;height:32px;border-radius:8px;background:rgba(139,92,246,0.15);text-align:center;vertical-align:middle;"><span style="color:#8B5CF6;font-size:14px;font-weight:800;line-height:32px;">2</span></td>
                <td style="padding-left:12px;"><p style="color:#334155;font-size:13px;margin:0;">Go to Settings and choose a plan</p></td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td>
              <table role="presentation" cellpadding="0" cellspacing="0"><tr>
                <td style="width:32px;height:32px;border-radius:8px;background:rgba(16,185,129,0.15);text-align:center;vertical-align:middle;"><span style="color:#10B981;font-size:14px;font-weight:800;line-height:32px;">3</span></td>
                <td style="padding-left:12px;"><p style="color:#334155;font-size:13px;margin:0;">Apply code <strong style="color:#10B981;">{discount_code}</strong> at checkout</p></td>
              </tr></table>
            </td>
          </tr>
        </table>
      </div>

      <!-- Support -->
      <div style="text-align:center;padding:20px 0 0;border-top:1px solid #1E293B;">
        <p style="color:#94A3B8;font-size:13px;line-height:1.6;margin:0 0 16px;">
          We're here to help if you need anything.<br/>
          Visit our <a href="mailto:support@realaicoach.app" style="color:#3B82F6;text-decoration:none;font-weight:600;">Customer Support</a> or contact us directly at <a href="mailto:support@realaicoach.app" style="color:#3B82F6;text-decoration:none;font-weight:600;">support@realaicoach.app</a>
        </p>
        <p style="color:#64748B;font-size:11px;margin:0;">We'd love to have you back soon.</p>
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div style="text-align:center;padding:24px 0;">
    <div style="height:3px;background:linear-gradient(90deg,#3B82F6,#8B5CF6,#EC4899,#06D6A0);border-radius:2px;margin-bottom:20px;"></div>
    <p style="font-size:18px;font-weight:900;letter-spacing:-0.5px;margin:0 0 6px;line-height:1;font-family:-apple-system,Helvetica,Arial,sans-serif;">
      <span style="color:#0F172A;">Real</span><span style="color:#06D6A0;">AI</span><span style="color:#0F172A;">Coach</span>
    </p>
    <p style="color:#475569;font-size:11px;margin:0 0 4px;">RealAICoach LLC &bull; 11501 Domain Dr, Suite 200, Austin, TX 78758, USA</p>
    <p style="color:#334155;font-size:10px;margin:0;">You received this email because your subscription was cancelled.</p>
  </div>
</div>
</body>
</html>"""


def _build_winback_reminder_html(user_name: str, discount_code: str, discount_expiry: str, reminder_number: int) -> str:
    """Bi-weekly win-back reminder email — varies messaging by attempt."""
    logo_html = render_email_logo(variant="default")
    headlines = [
        ("We Miss You!", "Your AI coaching journey doesn't have to end here."),
        ("Your Spot is Waiting", "Great things are happening at RealAICoach."),
        ("Don't Miss Out", "Your exclusive comeback offer is still active."),
        ("Last Chance Reminder", "Your discount code expires soon."),
        ("One More Thing...", "We've been making improvements you'll love."),
        ("Final Reminder", "This is your last reminder — we hope to see you again."),
    ]
    idx = min(reminder_number - 1, len(headlines) - 1)
    headline, subtext = headlines[idx]

    urgency_bar = ""
    if reminder_number >= 4:
        urgency_bar = f"""<div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);border-radius:10px;padding:14px 20px;margin:0 0 20px;text-align:center;">
          <p style="color:#EF4444;font-size:12px;font-weight:700;margin:0;">Your {DISCOUNT_PERCENT}% discount code expires on {discount_expiry}</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#FFFFFF;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 16px;">
  <div style="border-radius:20px;overflow:hidden;border:1px solid #E2E8F0;background:#FFFFFF;">
    <!-- Header -->
    <div style="background:linear-gradient(135deg,#2563EB 0%,#7C3AED 100%);padding:40px 32px;text-align:center;">
      {logo_html}
      <h1 style="color:#FFFFFF;font-size:26px;font-weight:800;margin:16px 0 8px;letter-spacing:-0.5px;">{headline}</h1>
      <p style="color:rgba(255,255,255,0.8);font-size:14px;margin:0;">{subtext}</p>
    </div>

    <div style="padding:32px;">
      <p style="color:#334155;font-size:15px;line-height:1.7;margin:0 0 20px;">Hi {user_name},</p>
      <p style="color:#475569;font-size:14px;line-height:1.7;margin:0 0 20px;">
        We noticed you haven't been back since cancelling your subscription. We understand — but we want you to know your {DISCOUNT_PERCENT}% comeback discount is still waiting for you.
      </p>

      {urgency_bar}

      <!-- Discount Code -->
      <div style="background:#F8FAFC;border-radius:14px;padding:24px;border:1px solid #E2E8F0;text-align:center;margin:0 0 24px;">
        <p style="color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin:0 0 8px;">YOUR COMEBACK CODE</p>
        <p style="color:#10B981;font-size:28px;font-weight:800;letter-spacing:4px;margin:0 0 8px;">{discount_code}</p>
        <p style="color:#64748B;font-size:11px;margin:0;">Valid until {discount_expiry} &middot; {DISCOUNT_PERCENT}% off any plan</p>
      </div>

      <div style="text-align:center;">
        <a href="mailto:support@realaicoach.app" style="color:#3B82F6;font-size:13px;text-decoration:none;">Need help? Contact support@realaicoach.app</a>
      </div>
    </div>
  </div>
  <div style="text-align:center;padding:20px 0;">
    <div style="height:3px;background:linear-gradient(90deg,#3B82F6,#8B5CF6,#EC4899,#06D6A0);border-radius:2px;margin-bottom:20px;"></div>
    <p style="font-size:18px;font-weight:900;letter-spacing:-0.5px;margin:0 0 6px;line-height:1;font-family:-apple-system,Helvetica,Arial,sans-serif;">
      <span style="color:#0F172A;">Real</span><span style="color:#06D6A0;">AI</span><span style="color:#0F172A;">Coach</span>
    </p>
    <p style="color:#475569;font-size:11px;margin:0 0 4px;">RealAICoach LLC &bull; 11501 Domain Dr, Suite 200, Austin, TX 78758, USA</p>
    <p style="color:#334155;font-size:10px;margin:0;">You received this because you previously subscribed to RealAICoach.</p>
  </div>
</div>
</body>
</html>"""


async def handle_subscription_cancellation(user_id: str, user_email: str, user_name: str):
    """Called when a user cancels their subscription. Sends immediate email + schedules win-back."""
    now = datetime.now(timezone.utc)
    discount_code = _generate_discount_code()
    discount_expiry = (now + timedelta(days=DISCOUNT_VALIDITY_DAYS)).strftime("%B %d, %Y")

    # Store churn record
    churn_record = {
        "churn_id": f"churn_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "user_email": user_email,
        "user_name": user_name,
        "cancelled_at": now.isoformat(),
        "discount_code": discount_code,
        "discount_expiry": (now + timedelta(days=DISCOUNT_VALIDITY_DAYS)).isoformat(),
        "discount_percent": DISCOUNT_PERCENT,
        "discount_redeemed": False,
        "status": "churned",  # churned | winback_sent | recovered | expired
        "reminders_sent": 0,
        "last_reminder_at": None,
        "next_reminder_at": (now + timedelta(days=REMINDER_INTERVAL_DAYS)).isoformat(),
        "email_history": [],
        "recovered_at": None,
    }
    await db.churn_recovery.insert_one(churn_record)

    # Send immediate cancellation email
    _build_cancellation_email_html(user_name, discount_code, discount_expiry)
    from utils.email_service import send_catalog_template
    result = await send_catalog_template(
        recipient_email=user["email"],
        template_key="churn_winback",
        recipient_name=user.get("name", ""),
        user_name=user.get("name", "there"),
        days_inactive=days_gone,
        special_offer=offer_text,
    )

    # Track email send
    await db.churn_recovery.update_one(
        {"churn_id": churn_record["churn_id"]},
        {
            "$push": {
                "email_history": {
                    "type": "cancellation",
                    "sent_at": now.isoformat(),
                    "success": result.get("success", False),
                    "message_id": result.get("message_id", ""),
                }
            }
        },
    )

    logger.info(f"Churn recovery initiated for {user_email}: code={discount_code}")
    return churn_record["churn_id"]


async def send_winback_reminders():
    """Scheduled job: send bi-weekly win-back reminders to churned users."""
    now = datetime.now(timezone.utc)
    sent_count = 0

    # Find users due for a reminder
    due_records = await db.churn_recovery.find(
        {
            "status": {"$in": ["churned", "winback_sent"]},
            "reminders_sent": {"$lt": MAX_REMINDERS},
            "next_reminder_at": {"$lte": now.isoformat()},
        },
        {"_id": 0},
    ).to_list(200)

    for record in due_records:
        user_id = record["user_id"]

        # Check if user resubscribed
        active_sub = await db.subscriptions.find_one({"user_id": user_id, "status": "active"}, {"_id": 0})
        if active_sub:
            await db.churn_recovery.update_one(
                {"churn_id": record["churn_id"]}, {"$set": {"status": "recovered", "recovered_at": now.isoformat()}}
            )
            continue

        reminder_num = record.get("reminders_sent", 0) + 1
        discount_expiry = datetime.fromisoformat(record["discount_expiry"].replace("Z", "+00:00")).strftime("%B %d, %Y")

        # Check if discount expired — extend it for active campaigns
        if now.isoformat() > record["discount_expiry"]:
            new_expiry = (now + timedelta(days=DISCOUNT_VALIDITY_DAYS)).isoformat()
            discount_expiry = (now + timedelta(days=DISCOUNT_VALIDITY_DAYS)).strftime("%B %d, %Y")
            await db.churn_recovery.update_one(
                {"churn_id": record["churn_id"]}, {"$set": {"discount_expiry": new_expiry}}
            )

        _build_winback_reminder_html(record["user_name"], record["discount_code"], discount_expiry, reminder_num)

        subjects = [
            f"We Miss You, {record['user_name']}! Your {DISCOUNT_PERCENT}% Discount Awaits",
            f"Your Spot at RealAICoach is Waiting - {DISCOUNT_PERCENT}% Off Inside",
            f"Don't Forget Your {DISCOUNT_PERCENT}% Comeback Discount",
            f"Last Chance: Your {DISCOUNT_PERCENT}% Discount Expires Soon",
            "We've Been Improving - Come See What's New",
            f"Final Reminder: Your {DISCOUNT_PERCENT}% Off Code is Expiring",
        ]
        subjects[min(reminder_num - 1, len(subjects) - 1)]

        result = await send_catalog_template(
            recipient_email=record["user_email"],
            template_key="winback_reminder_v7",
            recipient_name=record["user_name"],
            user_name=record["user_name"],
            discount_pct=DISCOUNT_PERCENT,
            discount_code=record["discount_code"],
            discount_expiry=discount_expiry,
            reminder_number=reminder_num,
        )

        next_reminder = (now + timedelta(days=REMINDER_INTERVAL_DAYS)).isoformat()
        new_status = "winback_sent" if reminder_num < MAX_REMINDERS else "expired"

        await db.churn_recovery.update_one(
            {"churn_id": record["churn_id"]},
            {
                "$set": {
                    "reminders_sent": reminder_num,
                    "last_reminder_at": now.isoformat(),
                    "next_reminder_at": next_reminder if new_status != "expired" else None,
                    "status": new_status,
                },
                "$push": {
                    "email_history": {
                        "type": f"reminder_{reminder_num}",
                        "sent_at": now.isoformat(),
                        "success": result.get("success", False),
                        "message_id": result.get("message_id", ""),
                    }
                },
            },
        )
        sent_count += 1

    logger.info(f"Win-back reminders sent: {sent_count}")
    return sent_count
