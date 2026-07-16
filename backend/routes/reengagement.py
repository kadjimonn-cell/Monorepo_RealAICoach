"""User Re-engagement: multi-tier automated emails + win-back offers + admin analytics."""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from routes.db import db, require_admin
from utils.email_service import is_email_configured, render_email_logo, FRONTEND_BASE_URL
from routes.ab_testing import get_active_test_for_tier, assign_variant, get_promoted_default_for_tier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reengagement", tags=["reengagement"])

# ─── Multi-Tier Configuration ───
TIERS = [
    {"id": "tier1", "days": 30, "label": "Gentle Reminder", "color": "#3B82F6", "cooldown": 25},
    {"id": "tier2", "days": 60, "label": "Urgent Nudge", "color": "#F59E0B", "cooldown": 25},
    {"id": "tier3", "days": 90, "label": "Win-Back Offer", "color": "#EF4444", "cooldown": 25},
]


def _get_tier(days_inactive: int):
    if days_inactive >= 90:
        return TIERS[2]
    elif days_inactive >= 60:
        return TIERS[1]
    elif days_inactive >= 30:
        return TIERS[0]
    return None


# ─── Email Templates ───


def _common_footer(email: str) -> str:
    from utils.email_templates import render_global_email_footer

    return render_global_email_footer(
        theme="light",
        variant="full",
        recipient_email=email,
        reason="you have an active account on RealAICoach",
    )

    year = datetime.now().year
    base_url = os.environ.get("FRONTEND_BASE_URL", "").strip().rstrip("/")
    privacy_url = f"{base_url}/privacy-policy" if base_url else "#"
    terms_url = f"{base_url}/terms" if base_url else "#"
    gp_url = os.environ.get("GOOGLE_PLAY_URL", "https://play.google.com/store/apps/details?id=com.realaicoach.app")
    as_url = os.environ.get("APP_STORE_URL", "https://apps.apple.com/app/realaicoach/id6502293851")
    return f"""<tr><td style="padding:0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="height:3px;background:linear-gradient(90deg,#3B82F6,#8B5CF6,#EC4899,#06D6A0);font-size:0;line-height:0;">&nbsp;</td>
      </tr></table>
    </td></tr>
    <tr><td style="background:#F8FAFC;padding:24px 32px 16px;text-align:center;">
      <p style="color:#475569;font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin:0 0 8px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">Get the App</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 18px;">
        <tr>
          <td style="padding-right:8px;">
            <a href="{gp_url}" target="_blank" style="text-decoration:none;display:inline-block;">
              <table cellpadding="0" cellspacing="0" style="background:#000000;border-radius:10px;border:1.5px solid #A6A6A6;min-width:135px;">
                <tr><td style="padding:8px 14px 8px 10px;">
                  <table cellpadding="0" cellspacing="0"><tr>
                    <td style="vertical-align:middle;padding-right:8px;width:22px;">
                      <table cellpadding="0" cellspacing="0"><tr>
                        <td style="width:0;height:0;border-top:10px solid transparent;border-bottom:10px solid transparent;border-left:16px solid #34A853;font-size:0;line-height:0;"></td>
                      </tr></table>
                    </td>
                    <td style="vertical-align:middle;">
                      <span style="color:#FFFFFF;font-size:7px;font-weight:400;display:block;line-height:1;letter-spacing:0.8px;text-transform:uppercase;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">GET IT ON</span>
                      <span style="color:#FFFFFF;font-size:14px;font-weight:600;display:block;line-height:1.3;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;letter-spacing:-0.2px;">Google Play</span>
                    </td>
                  </tr></table>
                </td></tr>
              </table>
            </a>
          </td>
          <td style="padding-left:8px;">
            <a href="{as_url}" target="_blank" style="text-decoration:none;display:inline-block;">
              <table cellpadding="0" cellspacing="0" style="background:#000000;border-radius:10px;border:1.5px solid #A6A6A6;min-width:135px;">
                <tr><td style="padding:8px 14px 8px 10px;">
                  <table cellpadding="0" cellspacing="0"><tr>
                    <td style="vertical-align:middle;padding-right:8px;">
                      <img src="https://developer.apple.com/assets/elements/icons/app-store/app-store-128x128_2x.png" alt="Apple" width="22" height="22" style="display:block;width:22px;height:22px;border:0;" />
                    </td>
                    <td style="vertical-align:middle;">
                      <span style="color:#FFFFFF;font-size:7px;font-weight:400;display:block;line-height:1;letter-spacing:0.5px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">Download on the</span>
                      <span style="color:#FFFFFF;font-size:14px;font-weight:600;display:block;line-height:1.3;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;letter-spacing:-0.2px;">App Store</span>
                    </td>
                  </tr></table>
                </td></tr>
              </table>
            </a>
          </td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="background:#F8FAFC;padding:0 32px 24px;text-align:center;">
      <p style="font-size:18px;font-weight:900;letter-spacing:-0.5px;margin:0 0 8px;line-height:1;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
        <span style="color:#0F172A;">Real</span><span style="color:#06D6A0;">AI</span><span style="color:#0F172A;">Coach</span>
      </p>
      <p style="color:#64748B;font-size:11px;margin:0;line-height:1.8;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
        This email was sent to <strong>{email}</strong> because you have an active account on RealAICoach.<br>
        <a href="{privacy_url}" style="color:#3B82F6;text-decoration:underline;">Privacy Policy</a> &bull;
        <a href="{terms_url}" style="color:#3B82F6;text-decoration:underline;">Terms of Service</a><br>
        RealAICoach LLC &bull; 11501 Domain Dr, Suite 200, Austin, TX 78758, USA<br>
        &copy; {year} RealAICoach LLC. All rights reserved.
      </p>
    </td></tr>"""


def _stats_strip() -> str:
    return """<tr><td style="padding:0 36px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:14px;border:1px solid #E2E8F0;">
      <tr>
        <td style="padding:16px;text-align:center;width:33%;border-right:1px solid #E2E8F0;">
          <div style="color:#2563EB;font-size:22px;font-weight:800;">10K+</div>
          <div style="color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-top:3px;">Active Users</div>
        </td>
        <td style="padding:16px;text-align:center;width:33%;border-right:1px solid #E2E8F0;">
          <div style="color:#10B981;font-size:22px;font-weight:800;">58%</div>
          <div style="color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-top:3px;">Perf. Boost</div>
        </td>
        <td style="padding:16px;text-align:center;width:34%;">
          <div style="color:#F59E0B;font-size:22px;font-weight:800;">4.8/5</div>
          <div style="color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-top:3px;">User Rating</div>
        </td>
      </tr>
    </table>
  </td></tr>"""


def _build_tier1_html(name: str, email: str, days: int) -> str:
    """Tier 1 (30d): Gentle, friendly check-in."""
    logo = render_email_logo("default")
    login_url = f"{FRONTEND_BASE_URL}/auth/login"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:32px auto;background:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 4px 32px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 50%,#0F172A 100%);padding:40px 36px 32px;text-align:center;">
    {logo}
    <div style="display:inline-block;background:#3B82F6;color:#FFF;font-size:10px;font-weight:800;padding:5px 14px;border-radius:20px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:16px;">Friendly Reminder</div>
    <h1 style="color:#F8FAFC;font-size:26px;font-weight:800;margin:12px 0 8px;letter-spacing:-0.5px;line-height:1.3;">Hey {name}, we noticed you've been away!</h1>
    <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">It's been <strong style="color:#60A5FA;">{days} days</strong> since your last visit</p>
  </td></tr>
  <tr><td style="padding:28px 36px 0;">
    <h2 style="color:#0F172A;font-size:17px;font-weight:800;margin:0 0 18px;">Your coaching journey is waiting:</h2>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding-bottom:14px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#DBEAFE;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#2563EB;font-size:17px;">&#128161;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">New Insights Available</strong><br><span style="color:#64748B;font-size:12px;">AI-generated coaching recommendations personalized for you</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:14px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#10B981;font-size:17px;">&#128200;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Your Progress Dashboard</strong><br><span style="color:#64748B;font-size:12px;">Check your performance metrics and growth trajectory</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:4px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#EDE9FE;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#7C3AED;font-size:17px;">&#128218;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Fresh Content Added</strong><br><span style="color:#64748B;font-size:12px;">New resources and guides tailored to your career goals</span></td>
        </tr></table>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:32px 36px;text-align:center;">
    <a href="{login_url}" style="display:inline-block;background:linear-gradient(135deg,#2563EB,#3B82F6);color:#FFFFFF;font-size:16px;font-weight:700;padding:16px 48px;border-radius:12px;text-decoration:none;letter-spacing:0.3px;box-shadow:0 4px 16px rgba(37,99,235,0.35);">
      Check In Now &#8594;
    </a>
    <p style="color:#94A3B8;font-size:12px;margin:14px 0 0;">Just a quick visit to stay on track</p>
  </td></tr>
  {_stats_strip()}
  {_common_footer(email)}
</table></body></html>"""


def _build_tier2_html(name: str, email: str, days: int) -> str:
    """Tier 2 (60d): Urgent, highlights missed opportunities."""
    logo = render_email_logo("default")
    login_url = f"{FRONTEND_BASE_URL}/auth/login"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:32px auto;background:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 4px 32px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 50%,#0F172A 100%);padding:40px 36px 32px;text-align:center;">
    {logo}
    <div style="display:inline-block;background:#F59E0B;color:#0F172A;font-size:10px;font-weight:800;padding:5px 14px;border-radius:20px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:16px;">Action Needed</div>
    <h1 style="color:#F8FAFC;font-size:26px;font-weight:800;margin:12px 0 8px;letter-spacing:-0.5px;line-height:1.3;">We Miss You, {name}!</h1>
    <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">It's been <strong style="color:#F59E0B;">{days} days</strong> since your last visit</p>
  </td></tr>
  <tr><td style="padding:24px 36px 0;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#FEF3C7,#FDE68A);border-radius:14px;border:1px solid #E8C848;">
      <tr><td style="padding:18px 22px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:42px;height:42px;background:#F59E0B;border-radius:12px;text-align:center;vertical-align:middle;"><span style="color:#FFF;font-size:20px;">&#9888;</span></td>
          <td style="padding-left:16px;">
            <div style="color:#92400E;font-size:14px;font-weight:700;">Your growth momentum has stalled</div>
            <div style="color:#A16207;font-size:12px;margin-top:3px;line-height:1.5;">Consistent engagement is key to achieving your coaching goals. Don't let your progress slip away.</div>
          </td>
        </tr></table>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:28px 36px 0;">
    <h2 style="color:#0F172A;font-size:17px;font-weight:800;margin:0 0 18px;">Here's what you're missing:</h2>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding-bottom:14px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#DBEAFE;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#2563EB;font-size:17px;">&#128640;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">New AI Features Launched</strong><br><span style="color:#64748B;font-size:12px;">Enhanced coaching tools and smarter insights await you</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:14px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#10B981;font-size:17px;">&#128200;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Your Peers Are Advancing</strong><br><span style="color:#64748B;font-size:12px;">Active users have completed 200+ coaching sessions this month</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:14px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#FEF3C7;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#F59E0B;font-size:17px;">&#127942;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Leaderboard Updated</strong><br><span style="color:#64748B;font-size:12px;">Jump back in and reclaim your ranking among top performers</span></td>
        </tr></table>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:32px 36px;text-align:center;">
    <a href="{login_url}" style="display:inline-block;background:linear-gradient(135deg,#D97706,#F59E0B);color:#0F172A;font-size:16px;font-weight:700;padding:16px 48px;border-radius:12px;text-decoration:none;letter-spacing:0.3px;box-shadow:0 4px 16px rgba(245,158,11,0.35);">
      Resume Your Journey &#8594;
    </a>
    <p style="color:#94A3B8;font-size:12px;margin:14px 0 0;">It only takes 30 seconds to pick up where you left off</p>
  </td></tr>
  {_stats_strip()}
  {_common_footer(email)}
</table></body></html>"""


def _build_tier3_html(name: str, email: str, days: int, promo_code: str) -> str:
    """Tier 3 (90d): Final effort with win-back Premium offer."""
    logo = render_email_logo("default")
    login_url = f"{FRONTEND_BASE_URL}/auth/login?promo={promo_code}"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:32px auto;background:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 4px 32px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 50%,#0F172A 100%);padding:40px 36px 32px;text-align:center;">
    {logo}
    <div style="display:inline-block;background:#EF4444;color:#FFF;font-size:10px;font-weight:800;padding:5px 14px;border-radius:20px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:16px;">Final Notice</div>
    <h1 style="color:#F8FAFC;font-size:26px;font-weight:800;margin:12px 0 8px;letter-spacing:-0.5px;line-height:1.3;">Don't Let Your Account Go Inactive, {name}</h1>
    <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">It's been <strong style="color:#EF4444;">{days} days</strong> since your last visit</p>
  </td></tr>

  <!-- Win-Back Offer Banner -->
  <tr><td style="padding:24px 36px 0;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#EDE9FE,#DDD6FE);border-radius:16px;border:2px solid #A78BFA;overflow:hidden;">
      <tr><td style="padding:24px 26px;">
        <div style="text-align:center;">
          <div style="display:inline-block;background:#8B5CF6;color:#FFF;font-size:10px;font-weight:800;padding:4px 12px;border-radius:12px;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">Exclusive Offer</div>
          <h2 style="color:#4C1D95;font-size:24px;font-weight:800;margin:8px 0 6px;line-height:1.2;">Get 1 Month FREE Premium</h2>
          <p style="color:#6D28D9;font-size:13px;margin:0 0 16px;line-height:1.5;">We want you back! Come back today and enjoy all Premium features for an entire month, completely free.</p>
          <table cellpadding="0" cellspacing="0" style="margin:0 auto;background:#F5F3FF;border-radius:10px;border:1px dashed #A78BFA;">
            <tr><td style="padding:12px 24px;">
              <div style="color:#6D28D9;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Your Promo Code</div>
              <div style="color:#4C1D95;font-size:22px;font-weight:900;letter-spacing:2px;margin-top:4px;">{promo_code}</div>
            </td></tr>
          </table>
        </div>
      </td></tr>
    </table>
  </td></tr>

  <!-- Urgency Alert -->
  <tr><td style="padding:20px 36px 0;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#FEE2E2,#FECACA);border-radius:14px;border:1px solid #F87171;">
      <tr><td style="padding:16px 22px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:42px;height:42px;background:#EF4444;border-radius:12px;text-align:center;vertical-align:middle;"><span style="color:#FFF;font-size:20px;">&#9200;</span></td>
          <td style="padding-left:16px;">
            <div style="color:#991B1B;font-size:14px;font-weight:700;">Your coaching progress is at risk</div>
            <div style="color:#B91C1C;font-size:12px;margin-top:3px;line-height:1.5;">Without regular engagement, you may miss critical opportunities for professional growth and networking.</div>
          </td>
        </tr></table>
      </td></tr>
    </table>
  </td></tr>

  <!-- Premium Benefits -->
  <tr><td style="padding:24px 36px 0;">
    <h2 style="color:#0F172A;font-size:17px;font-weight:800;margin:0 0 18px;">What you'll unlock with Premium:</h2>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding-bottom:12px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#DBEAFE;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#2563EB;font-size:17px;">&#9889;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Unlimited AI Coaching Sessions</strong><br><span style="color:#64748B;font-size:12px;">Get personalized coaching from Nova AI without limits</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:12px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#10B981;font-size:17px;">&#128640;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Priority Access to New Features</strong><br><span style="color:#64748B;font-size:12px;">Be the first to try AI tools, analytics, and reports</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:12px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#FEF3C7;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#F59E0B;font-size:17px;">&#127942;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Advanced Analytics & Reports</strong><br><span style="color:#64748B;font-size:12px;">Detailed performance insights and career tracking</span></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding-bottom:4px;">
        <table cellpadding="0" cellspacing="0"><tr>
          <td style="width:38px;height:38px;background:#EDE9FE;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#7C3AED;font-size:17px;">&#127775;</span></td>
          <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:13px;">Premium Badge & Leaderboard Boost</strong><br><span style="color:#64748B;font-size:12px;">Stand out in the community and get recognized</span></td>
        </tr></table>
      </td></tr>
    </table>
  </td></tr>

  <tr><td style="padding:32px 36px;text-align:center;">
    <a href="{login_url}" style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#8B5CF6);color:#FFFFFF;font-size:16px;font-weight:700;padding:16px 48px;border-radius:12px;text-decoration:none;letter-spacing:0.3px;box-shadow:0 4px 16px rgba(139,92,246,0.4);">
      Claim Your Free Month &#8594;
    </a>
    <p style="color:#94A3B8;font-size:12px;margin:14px 0 0;">Offer valid for 14 days. No credit card required.</p>
  </td></tr>
  {_stats_strip()}
  {_common_footer(email)}
</table></body></html>"""


def _get_email_for_tier(tier_id: str, name: str, email: str, days: int, promo_code: str = ""):
    if tier_id == "tier1":
        return _build_tier1_html(name, email, days), f"Hey {name}, we noticed you've been away ({days} days)"
    elif tier_id == "tier2":
        return _build_tier2_html(name, email, days), f"Your Action Needed - It's been {days} days, {name}!"
    else:
        return _build_tier3_html(name, email, days, promo_code), f"Final Notice: Claim your FREE Premium month, {name}!"


AB_TESTING_BASE = os.environ.get("FRONTEND_BASE_URL", "")


def _inject_ab_tracking(html: str, send_id: str, cta_text: str = "", cta_color: str = "") -> str:
    """Inject open-tracking pixel and replace CTA link with click-tracking URL."""
    tracking_pixel = f'<img src="{AB_TESTING_BASE}/api/ab-testing/track/open/{send_id}" width="1" height="1" alt="" style="display:none;" />'
    click_url = f"{AB_TESTING_BASE}/api/ab-testing/track/click/{send_id}"

    # Replace CTA link (auth/login) with tracked click URL
    import re

    html = re.sub(
        r'href="[^"]*?/auth/login[^"]*?"',
        f'href="{click_url}"',
        html,
    )

    # Replace CTA button text if provided
    if cta_text:
        # Match CTA button text patterns (the text inside the <a> button)
        for pattern in [
            r"(Check In Now\s*&#8594;)",
            r"(Resume Your Journey\s*&#8594;)",
            r"(Claim Your Free Month\s*&#8594;)",
        ]:
            html = re.sub(pattern, f"{cta_text} &#8594;", html)

    # Inject tracking pixel before closing </body>
    html = html.replace("</body>", f"{tracking_pixel}</body>")
    return html


async def _generate_promo_code(user_id: str) -> str:
    code = f"WINBACK-{uuid.uuid4().hex[:8].upper()}"
    await db.promo_codes.insert_one(
        {
            "code": code,
            "user_id": user_id,
            "type": "winback_premium_1m",
            "description": "1 Month Free Premium - Win-back Offer",
            "valid_days": 14,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "redeemed": False,
        }
    )
    return code


# ─── Scheduled Job ───


async def run_reengagement_check():
    """Daily job: process all 3 tiers of re-engagement emails with A/B test support."""
    if not is_email_configured():
        logger.warning("Reengagement: email not configured, skipping.")
        return

    now = datetime.now(timezone.utc)
    results = {"tier1": 0, "tier2": 0, "tier3": 0, "skipped": 0, "ab_variants": 0, "promoted": 0}

    for tier in TIERS:
        threshold = (now - timedelta(days=tier["days"])).isoformat()
        cooldown_cutoff = (now - timedelta(days=tier["cooldown"])).isoformat()

        # Check if there's an active A/B test for this tier
        ab_test = await get_active_test_for_tier(tier["id"])
        # Check for promoted defaults (used when no active A/B test)
        promoted_default = await get_promoted_default_for_tier(tier["id"]) if not ab_test else None

        inactive_users = await db.users.find(
            {"last_active_at": {"$lt": threshold, "$ne": ""}, "email_verified": {"$ne": False}},
            {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "first_name": 1, "last_active_at": 1},
        ).to_list(500)

        for user in inactive_users:
            user_id = user.get("user_id")
            email = user.get("email")
            if not user_id or not email:
                continue

            # Check if this tier was already sent within cooldown
            already = await db.reengagement_log.find_one(
                {"user_id": user_id, "tier": tier["id"], "sent_at": {"$gt": cooldown_cutoff}},
                {"_id": 0},
            )
            if already:
                results["skipped"] += 1
                continue

            last_active = user.get("last_active_at", "")
            last_active_str = str(last_active or "")
            try:
                last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                days_inactive = (now - last_dt).days
            except Exception:
                days_inactive = tier["days"]

            # Only send if user falls into this specific tier bracket
            current_tier = _get_tier(days_inactive)
            if not current_tier or current_tier["id"] != tier["id"]:
                continue

            name = user.get("first_name") or (
                user.get("full_name", "").split()[0] if user.get("full_name") else "there"
            )

            promo_code = ""
            if tier["id"] == "tier3":
                promo_code = await _generate_promo_code(user_id)

            html, subject = _get_email_for_tier(tier["id"], name, email, days_inactive, promo_code)

            # Apply promoted defaults (from previous A/B test winners) when no active test
            if promoted_default and not ab_test:
                import re as _re

                if promoted_default.get("subject_line"):
                    (
                        promoted_default["subject_line"].replace("{name}", name).replace("{days}", str(days_inactive))
                    )
                if promoted_default.get("cta_text"):
                    cta = promoted_default["cta_text"]
                    for pat in [
                        r"Check In Now\s*&#8594;",
                        r"Resume Your Journey\s*&#8594;",
                        r"Claim Your Free Month\s*&#8594;",
                    ]:
                        html = _re.sub(pat, f"{cta} &#8594;", html)
                results["promoted"] += 1

            # A/B test integration: override subject line / CTA if active test
            ab_send_id = None
            ab_variant_key = None
            if ab_test:
                variant_info = await assign_variant(user_id, tier["id"], ab_test["test_id"])
                if variant_info:
                    ab_send_id = variant_info["send_id"]
                    ab_variant_key = variant_info["variant_key"]
                    variant_data = variant_info["variant"]
                    # Override subject line from A/B variant
                    if variant_data.get("subject_line"):
                        (
                            variant_data["subject_line"].replace("{name}", name).replace("{days}", str(days_inactive))
                        )
                    # Inject tracking pixel, click tracking, and optional CTA override
                    html = _inject_ab_tracking(
                        html,
                        ab_send_id,
                        cta_text=variant_data.get("cta_text", ""),
                        cta_color=variant_data.get("cta_color", ""),
                    )
                    results["ab_variants"] += 1

            from utils.email_service import send_catalog_template
            result = await send_catalog_template(
                recipient_email=user["email"],
                template_key="reengagement_nudge",
                recipient_name=user.get("name", ""),
                user_name=user.get("name", "there"),
                last_activity=last_active_str,
                streak_count=user.get("streak", 0),
            )

            await db.reengagement_log.insert_one(
                {
                    "user_id": user_id,
                    "email": email,
                    "days_inactive": days_inactive,
                    "tier": tier["id"],
                    "tier_label": tier["label"],
                    "promo_code": promo_code or None,
                    "sent_at": now.isoformat(),
                    "success": result.get("success", False),
                    "message_id": result.get("message_id"),
                    "ab_test_id": ab_test["test_id"] if ab_test else None,
                    "ab_variant": ab_variant_key,
                    "ab_send_id": ab_send_id,
                }
            )

            if result.get("success"):
                results[tier["id"]] += 1
                # Update A/B test send with actual delivery timestamp
                if ab_send_id:
                    await db.ab_test_sends.update_one(
                        {"send_id": ab_send_id},
                        {"$set": {"sent_at": now.isoformat(), "delivered": True}},
                    )

    logger.info(f"Reengagement check: {results}")
    return results


# ─── Admin API Endpoints ───


@router.get("/analytics")
async def get_reengagement_analytics(request: Request):
    """Comprehensive multi-tier analytics for the admin dashboard."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    # 1. User activity buckets
    buckets = {}
    for label, days in [
        ("active_7d", 7),
        ("active_14d", 14),
        ("active_30d", 30),
        ("inactive_30d", 30),
        ("inactive_60d", 60),
        ("inactive_90d", 90),
    ]:
        cutoff = (now - timedelta(days=days)).isoformat()
        if label.startswith("active"):
            count = await db.users.count_documents({"last_active_at": {"$gte": cutoff}})
        else:
            count = await db.users.count_documents({"last_active_at": {"$lt": cutoff, "$ne": ""}})
        buckets[label] = count

    total_users = await db.users.count_documents({})
    never_active = await db.users.count_documents(
        {"$or": [{"last_active_at": {"$exists": False}}, {"last_active_at": ""}]}
    )
    buckets["total_users"] = total_users
    buckets["never_active"] = never_active

    # 2. Emails sent over time (last 12 weeks) broken down by tier
    email_trend = []
    for i in range(12):
        week_start = (now - timedelta(weeks=i + 1)).isoformat()
        week_end = (now - timedelta(weeks=i)).isoformat()
        week_data = {"week": (now - timedelta(weeks=i)).strftime("%b %d")}
        for tier in TIERS:
            cnt = await db.reengagement_log.count_documents(
                {"sent_at": {"$gte": week_start, "$lt": week_end}, "tier": tier["id"], "success": True}
            )
            week_data[tier["id"]] = cnt
        total = sum(week_data.get(t["id"], 0) for t in TIERS)
        week_data["total"] = total
        email_trend.append(week_data)
    email_trend.reverse()

    # 3. Tier breakdown totals
    tier_stats = []
    for tier in TIERS:
        sent = await db.reengagement_log.count_documents({"tier": tier["id"], "success": True})
        tier_stats.append(
            {"id": tier["id"], "label": tier["label"], "color": tier["color"], "days": tier["days"], "sent": sent}
        )

    # 4. Win-back promo stats
    total_promos = await db.promo_codes.count_documents({"type": "winback_premium_1m"})
    redeemed_promos = await db.promo_codes.count_documents({"type": "winback_premium_1m", "redeemed": True})

    # 5. Return rate
    recent_logs = await db.reengagement_log.find(
        {"success": True, "sent_at": {"$gte": (now - timedelta(days=90)).isoformat()}},
        {"_id": 0, "user_id": 1, "sent_at": 1},
    ).to_list(5000)
    returned = 0
    for log in recent_logs:
        uid = log.get("user_id")
        sent_at = log.get("sent_at", "")
        try:
            sent_dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
            window_end = (sent_dt + timedelta(days=14)).isoformat()
        except Exception:
            continue
        u = await db.users.find_one(
            {"user_id": uid, "last_active_at": {"$gte": sent_at, "$lte": window_end}}, {"_id": 0, "user_id": 1}
        )
        if u:
            returned += 1
    total_sent_90d = len(recent_logs)
    return_rate = round(returned / total_sent_90d * 100, 1) if total_sent_90d > 0 else 0

    # 6. Recent email log
    recent_emails = await db.reengagement_log.find({}, {"_id": 0}).sort("sent_at", -1).to_list(50)

    # 7. At-risk users by tier
    at_risk_users = []
    for tier in TIERS:
        lower = tier["days"]
        upper = lower + 30
        lower_cutoff = (now - timedelta(days=upper)).isoformat()
        upper_cutoff = (now - timedelta(days=lower)).isoformat()
        users = await db.users.find(
            {"last_active_at": {"$lt": upper_cutoff, "$gte": lower_cutoff, "$ne": ""}},
            {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "first_name": 1, "last_active_at": 1},
        ).to_list(50)
        cooldown_cutoff = (now - timedelta(days=tier["cooldown"])).isoformat()
        for u in users:
            already = await db.reengagement_log.find_one(
                {"user_id": u["user_id"], "tier": tier["id"], "sent_at": {"$gt": cooldown_cutoff}}, {"_id": 0}
            )
            try:
                last_dt = datetime.fromisoformat(u.get("last_active_at", "").replace("Z", "+00:00"))
                d = (now - last_dt).days
            except Exception:
                d = tier["days"]
            at_risk_users.append(
                {
                    "user_id": u["user_id"],
                    "email": u.get("email", ""),
                    "name": u.get("full_name") or u.get("first_name") or "Unknown",
                    "days_inactive": d,
                    "tier": tier["id"],
                    "tier_label": tier["label"],
                    "email_sent": bool(already),
                }
            )

    # 8. DAU trend (last 30 days)
    dau_trend = []
    for i in range(30):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        day_end = (day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
        count = await db.users.count_documents({"last_active_at": {"$gte": day_start, "$lt": day_end}})
        dau_trend.append({"date": day.strftime("%b %d"), "count": count})
    dau_trend.reverse()

    return {
        "buckets": buckets,
        "email_trend": email_trend,
        "tier_stats": tier_stats,
        "promo_stats": {"total": total_promos, "redeemed": redeemed_promos},
        "return_rate": return_rate,
        "returned_users": returned,
        "total_sent_90d": total_sent_90d,
        "recent_emails": recent_emails,
        "at_risk_users": at_risk_users,
        "dau_trend": dau_trend,
    }


class ManualSendRequest(BaseModel):
    user_id: str
    tier: str = "tier2"


@router.post("/send-manual")
async def send_manual_reengagement(body: ManualSendRequest, request: Request):
    """Admin: manually trigger a tiered re-engagement email."""
    await require_admin(request)
    user = await db.users.find_one(
        {"user_id": body.user_id},
        {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "first_name": 1, "last_active_at": 1},
    )
    if not user:
        raise HTTPException(404, "User not found")

    now = datetime.now(timezone.utc)
    last_active = user.get("last_active_at", "")
    last_active_str = str(last_active or "")
    try:
        last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
        days_inactive = (now - last_dt).days
    except Exception:
        days_inactive = 45

    name = user.get("first_name") or (user.get("full_name", "").split()[0] if user.get("full_name") else "there")
    email = user["email"]
    tier_id = body.tier if body.tier in ["tier1", "tier2", "tier3"] else "tier2"

    promo_code = ""
    if tier_id == "tier3":
        promo_code = await _generate_promo_code(user["user_id"])

    html, subject = _get_email_for_tier(tier_id, name, email, days_inactive, promo_code)

    from utils.email_service import send_catalog_template
    result = await send_catalog_template(
        recipient_email=user["email"],
        template_key="reengagement_nudge",
        recipient_name=user.get("name", ""),
        user_name=user.get("name", "there"),
        last_activity=last_active_str,
        streak_count=user.get("streak", 0),
    )

    await db.reengagement_log.insert_one(
        {
            "user_id": user["user_id"],
            "email": email,
            "days_inactive": days_inactive,
            "tier": tier_id,
            "tier_label": next((t["label"] for t in TIERS if t["id"] == tier_id), ""),
            "promo_code": promo_code or None,
            "sent_at": now.isoformat(),
            "success": result.get("success", False),
            "message_id": result.get("message_id"),
            "manual": True,
        }
    )

    return {"success": result.get("success", False), "message_id": result.get("message_id")}


@router.get("/preview-email")
async def preview_reengagement_email(request: Request, tier: str = "tier2"):
    """Admin: preview a specific tier's email template."""
    await require_admin(request)
    tier_id = tier if tier in ["tier1", "tier2", "tier3"] else "tier2"
    if tier_id == "tier1":
        html = _build_tier1_html("Demo User", "demo@example.com", 32)
    elif tier_id == "tier2":
        html = _build_tier2_html("Demo User", "demo@example.com", 63)
    else:
        html = _build_tier3_html("Demo User", "demo@example.com", 95, "WINBACK-DEMO1234")
    return {"html": html, "tier": tier_id}
