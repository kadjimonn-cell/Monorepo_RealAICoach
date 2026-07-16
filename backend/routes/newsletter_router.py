"""Newsletter subscription endpoints with unsubscribe, preferences, and tracking."""

import os
import uuid
import secrets
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
import routes.db as _db_mod
from routes.db import require_admin
from fastapi import Request
from utils.email_service import is_email_configured, render_email_logo
from utils.email_templates import _enterprise_footer, _premium_mini_footer
from utils.pagination import iter_find_paginated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/newsletter", tags=["newsletter"])

ALL_CATEGORIES = [
    "Industry Insights", "Product Update", "Tips & Tricks",
    "Research", "Company News", "Enterprise",
]

# Weekly briefing cadence — defaults to Tuesday 07:00 LOCAL. Subscribers
# can override via POST /api/newsletter/preferences/cadence.
_BRIEFING_WEEKDAY = 1  # 0 = Monday, 1 = Tuesday, ...
_BRIEFING_HOUR = 7
_PREFS_TOKEN_TTL_MINUTES = 60

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

BRAND = "RealAICoach"

# ── Subject-line A/B test (by local-hour cohort) ──────────────────────
# Each local-hour bucket has two variants; we split subscribers 50/50
# deterministically via a stable hash of (email, iso_week), so a given
# subscriber sees the SAME variant all week but may flip next week. This
# gives us clean per-variant open-rate measurement without random jitter.
#
# Winners are frozen per-bucket in ``_FROZEN_WINNERS`` (loaded from
# ``db.newsletter_ab_winners`` on startup and on every promote/revert
# call). When a bucket is frozen, all subscribers in that bucket
# receive the winning variant (no more split).
_FROZEN_WINNERS: dict[str, str] = {}

_SUBJECT_AB_VARIANTS: dict[str, dict[str, str]] = {
    "morning": {
        "A": "Good morning — your week in AI coaching",
        "B": f"Your morning read is here — {BRAND} Weekly",
    },
    "afternoon": {
        "A": f"Your afternoon read — this week at {BRAND}",
        "B": f"Quick break? Here's your {BRAND} Weekly",
    },
    "evening": {
        "A": f"Your evening read — this week at {BRAND}",
        "B": f"Wind down with this week's {BRAND} briefing",
    },
    "night": {
        "A": f"Tonight's briefing — this week at {BRAND}",
        "B": f"Before you sleep — this week at {BRAND}",
    },
}


def _hour_bucket(local_hour: int) -> str:
    """Map a 0–23 local hour into a coarse time-of-day bucket."""
    h = int(local_hour) % 24
    if 5 <= h <= 11:
        return "morning"
    if 12 <= h <= 16:
        return "afternoon"
    if 17 <= h <= 21:
        return "evening"
    return "night"


def _pick_subject_variant(
    email: str, iso_year: int, iso_week: int, local_hour: int
) -> dict:
    """Deterministically pick an A/B subject for this (email, week, hour).

    Returns ``{"variant": "A"|"B", "bucket": "morning"|..., "subject": str}``.
    A given subscriber gets the SAME variant for every tick inside the
    same ISO week, which keeps our A/B measurement clean (no mid-week
    variant flipping that would confuse attribution).

    If the bucket has a frozen winner (see ``/ab/promote-winner``), that
    variant is returned for every subscriber in the bucket — the test
    is over, ship the winner to 100%.
    """
    bucket = _hour_bucket(local_hour)
    frozen = _FROZEN_WINNERS.get(bucket)
    if frozen in ("A", "B"):
        subject = _SUBJECT_AB_VARIANTS[bucket][frozen]
        return {
            "variant": frozen,
            "bucket": bucket,
            "subject": subject,
            "frozen": True,
        }
    seed = f"{(email or '').strip().lower()}:{iso_year}-W{iso_week:02d}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    variant = "A" if digest[0] % 2 == 0 else "B"
    subject = _SUBJECT_AB_VARIANTS[bucket][variant]
    return {"variant": variant, "bucket": bucket, "subject": subject}


def _next_briefing_for_tz(
    tz_name: str,
    now_utc: Optional[datetime] = None,
    weekday: int = _BRIEFING_WEEKDAY,
    hour: int = _BRIEFING_HOUR,
) -> Optional[dict]:
    """Return a dict describing the next ``(weekday, hour)`` delivery in
    the subscriber's timezone, or ``None`` if the TZ name is invalid.

    ``weekday`` is 0-indexed from Monday (Python convention).
    """
    if not tz_name or len(tz_name) > 80:
        return None
    if not (0 <= weekday <= 6 and 0 <= hour <= 23):
        return None
    try:
        tz = ZoneInfo(str(tz_name).strip())
    except (ZoneInfoNotFoundError, Exception):
        return None

    now = (now_utc or datetime.now(timezone.utc)).astimezone(tz)
    days_ahead = (weekday - now.weekday()) % 7
    candidate = now.replace(
        hour=hour, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_ahead)
    # If today IS the target weekday but the hour has already passed, roll.
    if days_ahead == 0 and now >= candidate:
        candidate = candidate + timedelta(days=7)

    city = tz_name.rsplit("/", 1)[-1].replace("_", " ")
    # Format: "Tuesday · 7:00 AM (Los Angeles)"
    hour_12 = hour % 12 or 12
    ampm = "AM" if hour < 12 else "PM"
    display = (
        f"{_WEEKDAY_NAMES[weekday]} · {hour_12}:00 {ampm} ({city})"
    )
    return {
        "iso": candidate.isoformat(),
        "tz": tz_name,
        "display": display,
        "weekday": weekday,
        "hour": hour,
    }


def _new_prefs_token() -> tuple[str, str]:
    """Return (token, token_expires_at_iso) valid for TTL minutes."""
    token = secrets.token_urlsafe(24)
    exp = datetime.now(timezone.utc) + timedelta(minutes=_PREFS_TOKEN_TTL_MINUTES)
    return token, exp.isoformat()


def _make_token(email: str) -> str:
    """Generate a simple HMAC token for unsubscribe/preference links."""
    secret = str(os.environ.get("JWT_SECRET") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET is missing or too short for secure newsletter token generation")
    return hashlib.sha256(f"{email}:{secret}".encode()).hexdigest()[:24]


class SubscribeRequest(BaseModel):
    email: EmailStr
    source: str = "footer"
    subscription_type: str = "platform"  # "platform" or "blog"
    timezone: Optional[str] = None  # IANA TZ name from the browser, e.g. "America/Los_Angeles"


class SubscribeResponse(BaseModel):
    success: bool
    message: str
    already_subscribed: bool = False
    next_briefing_local: Optional[str] = None
    next_briefing_iso: Optional[str] = None
    next_briefing_tz: Optional[str] = None
    # Short-lived token (60 min TTL) that grants the JUST-subscribed
    # visitor the ability to change their briefing cadence from the
    # success card WITHOUT re-authenticating. The token is bound to the
    # email and stored server-side (not a self-signed JWT).
    preferences_token: Optional[str] = None
    preferred_weekday: Optional[int] = None
    preferred_hour: Optional[int] = None


class CadencePreferenceRequest(BaseModel):
    email: EmailStr
    token: str = Field(..., min_length=8, max_length=128)
    weekday: int = Field(..., ge=0, le=6)
    hour: int = Field(..., ge=0, le=23)
    timezone: Optional[str] = None


class CadencePreferenceResponse(BaseModel):
    success: bool
    message: str
    next_briefing_local: Optional[str] = None
    next_briefing_iso: Optional[str] = None
    next_briefing_tz: Optional[str] = None
    preferred_weekday: int
    preferred_hour: int


class PreferencesRequest(BaseModel):
    email: EmailStr
    token: str
    categories: list[str]


def _build_welcome_html(email: str) -> str:
    logo = render_email_logo("default")
    base_url = os.environ.get("FRONTEND_BASE_URL", "")
    login_url = f"{base_url}/auth/login"
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:40px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">
        <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);padding:40px 32px 32px;text-align:center;">
          {logo}
          <h1 style="color:#F8FAFC;font-size:24px;font-weight:800;margin:16px 0 8px;letter-spacing:-0.3px;">Welcome to the Inner Circle</h1>
          <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">You're now part of a select group shaping the future of AI coaching.</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="padding-bottom:24px;">
              <h2 style="color:#0F172A;font-size:18px;font-weight:700;margin:0 0 12px;">Here's what you'll get:</h2>
            </td></tr>
            <tr><td style="padding-bottom:16px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#10B981;font-size:16px;">&#10003;</span></td>
                <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:14px;">Early Access</strong><br><span style="color:#64748B;font-size:13px;">Be first to try new AI coaching features</span></td>
              </tr></table>
            </td></tr>
            <tr><td style="padding-bottom:16px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;background:#EFF6FF;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#3B82F6;font-size:16px;">&#9733;</span></td>
                <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:14px;">Expert Insights</strong><br><span style="color:#64748B;font-size:13px;">Curated tips from top AI and coaching professionals</span></td>
              </tr></table>
            </td></tr>
            <tr><td style="padding-bottom:16px;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;height:36px;background:#FFF7ED;border-radius:10px;text-align:center;vertical-align:middle;"><span style="color:#F97316;font-size:16px;">&#9889;</span></td>
                <td style="padding-left:14px;"><strong style="color:#1E293B;font-size:14px;">Exclusive Content</strong><br><span style="color:#64748B;font-size:13px;">Industry reports, webinar invites, and more</span></td>
              </tr></table>
            </td></tr>
          </table>
          <div style="text-align:center;margin-top:28px;">
            <a href="{login_url}" style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:14px;font-weight:700;padding:14px 36px;border-radius:10px;text-decoration:none;letter-spacing:0.3px;">Explore the Platform</a>
          </div>
        </td></tr>
        {_enterprise_footer("light")}
      </table>
    </body>
    </html>
    """


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(req: SubscribeRequest):
    email = req.email.strip().lower()
    sub_type = req.subscription_type if req.subscription_type in ("platform", "blog") else "platform"

    existing = await _db_mod.db.newsletter_subscribers.find_one(
        {"email": email},
        {"_id": 0, "email": 1, "subscription_type": 1, "timezone": 1,
         "preferred_weekday": 1, "preferred_hour": 1},
    )
    # Issue a fresh short-lived token — both new and returning subscribers
    # get one so they can tune their cadence from the success card.
    new_token, token_exp = _new_prefs_token()

    if existing:
        preferred_weekday = int(existing.get("preferred_weekday") or _BRIEFING_WEEKDAY)
        preferred_hour = int(existing.get("preferred_hour") or _BRIEFING_HOUR)
        active_tz = req.timezone or existing.get("timezone")
        briefing = _next_briefing_for_tz(active_tz, weekday=preferred_weekday, hour=preferred_hour) if active_tz else None

        upd = {"prefs_token": new_token, "prefs_token_expires_at": token_exp}
        if req.timezone and existing.get("timezone") != req.timezone:
            upd["timezone"] = req.timezone
        existing_type = existing.get("subscription_type", "platform")
        if existing_type != sub_type and existing_type != "all":
            upd["subscription_type"] = "all"
            await _db_mod.db.newsletter_subscribers.update_one({"email": email}, {"$set": upd})
            return SubscribeResponse(
                success=True,
                message="You're now subscribed to all our newsletters!",
                already_subscribed=True,
                next_briefing_local=(briefing or {}).get("display"),
                next_briefing_iso=(briefing or {}).get("iso"),
                next_briefing_tz=(briefing or {}).get("tz"),
                preferences_token=new_token,
                preferred_weekday=preferred_weekday,
                preferred_hour=preferred_hour,
            )
        await _db_mod.db.newsletter_subscribers.update_one({"email": email}, {"$set": upd})
        return SubscribeResponse(
            success=True,
            message="You're already on the list! We'll keep you posted.",
            already_subscribed=True,
            next_briefing_local=(briefing or {}).get("display"),
            next_briefing_iso=(briefing or {}).get("iso"),
            next_briefing_tz=(briefing or {}).get("tz"),
            preferences_token=new_token,
            preferred_weekday=preferred_weekday,
            preferred_hour=preferred_hour,
        )

    briefing = _next_briefing_for_tz(req.timezone) if req.timezone else None
    await _db_mod.db.newsletter_subscribers.insert_one(
        {
            "email": email,
            "subscribed_at": datetime.now(timezone.utc).isoformat(),
            "source": req.source,
            "subscription_type": sub_type,
            "status": "active",
            "categories": ALL_CATEGORIES.copy(),
            "timezone": req.timezone or None,
            "preferred_weekday": _BRIEFING_WEEKDAY,
            "preferred_hour": _BRIEFING_HOUR,
            "prefs_token": new_token,
            "prefs_token_expires_at": token_exp,
        }
    )

    if is_email_configured():
        try:
            from utils.email_service import send_catalog_template
            base_url = os.environ.get("FRONTEND_BASE_URL", "")
            await send_catalog_template(
                recipient_email=email,
                template_key="newsletter_welcome",
                login_url=f"{base_url}/auth/login" if base_url else "",
            )
        except Exception as exc:
            logger.warning(f"Newsletter welcome email failed for {email}: {exc}")

    return SubscribeResponse(
        success=True,
        message="You're in! Check your inbox for a welcome surprise.",
        next_briefing_local=(briefing or {}).get("display"),
        next_briefing_iso=(briefing or {}).get("iso"),
        next_briefing_tz=(briefing or {}).get("tz"),
        preferences_token=new_token,
        preferred_weekday=_BRIEFING_WEEKDAY,
        preferred_hour=_BRIEFING_HOUR,
    )


@router.post("/preferences/cadence", response_model=CadencePreferenceResponse)
async def set_briefing_cadence(req: CadencePreferenceRequest):
    """Set the subscriber's preferred weekly-briefing day + hour. Authed
    by a short-lived ``prefs_token`` the subscribe endpoint handed the
    visitor on the success card — no session cookie required, so this
    works for the just-subscribed anonymous user."""
    email = req.email.strip().lower()
    sub = await _db_mod.db.newsletter_subscribers.find_one(
        {"email": email},
        {"_id": 0, "email": 1, "prefs_token": 1, "prefs_token_expires_at": 1, "timezone": 1},
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Token check: exact match + not expired.
    expected = sub.get("prefs_token") or ""
    expires_at = sub.get("prefs_token_expires_at") or ""
    if not expected or req.token != expected:
        raise HTTPException(status_code=401, detail="Invalid or expired preferences token")
    try:
        if expires_at:
            exp_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= exp_dt:
                raise HTTPException(status_code=401, detail="Preferences token has expired")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token expiry on record")

    tz_name = req.timezone or sub.get("timezone")
    briefing = _next_briefing_for_tz(tz_name, weekday=req.weekday, hour=req.hour) if tz_name else None

    update = {
        "preferred_weekday": int(req.weekday),
        "preferred_hour": int(req.hour),
        "preferences_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if req.timezone:
        update["timezone"] = req.timezone
    await _db_mod.db.newsletter_subscribers.update_one({"email": email}, {"$set": update})

    return CadencePreferenceResponse(
        success=True,
        message="Briefing cadence saved.",
        next_briefing_local=(briefing or {}).get("display"),
        next_briefing_iso=(briefing or {}).get("iso"),
        next_briefing_tz=(briefing or {}).get("tz"),
        preferred_weekday=int(req.weekday),
        preferred_hour=int(req.hour),
    )


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(email: str = Query(...), token: str = Query(...)):
    """One-click unsubscribe via email link."""
    expected = _make_token(email)
    if token != expected:
        return HTMLResponse(_unsubscribe_page(email, success=False, error="Invalid link. Please use the link from your email."), status_code=400)

    result = await _db_mod.db.newsletter_subscribers.update_one(
        {"email": email.lower(), "status": "active"},
        {"$set": {"status": "unsubscribed", "unsubscribed_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        return HTMLResponse(_unsubscribe_page(email, success=True, already=True))
    return HTMLResponse(_unsubscribe_page(email, success=True))


@router.post("/resubscribe")
async def resubscribe(req: SubscribeRequest):
    """Re-subscribe a previously unsubscribed email."""
    email = req.email.strip().lower()
    result = await _db_mod.db.newsletter_subscribers.update_one(
        {"email": email, "status": "unsubscribed"},
        {"$set": {"status": "active", "resubscribed_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count > 0:
        return {"success": True, "message": "Welcome back! You've been re-subscribed."}
    existing = await _db_mod.db.newsletter_subscribers.find_one({"email": email, "status": "active"})
    if existing:
        return {"success": True, "message": "You're already subscribed!"}
    return {"success": False, "message": "No subscription found for this email."}


@router.get("/preferences")
async def get_preferences(email: str = Query(...), token: str = Query(...)):
    """Get subscriber preferences."""
    expected = _make_token(email)
    if token != expected:
        return {"success": False, "error": "Invalid token"}

    sub = await _db_mod.db.newsletter_subscribers.find_one(
        {"email": email.lower()}, {"_id": 0, "email": 1, "status": 1, "categories": 1}
    )
    if not sub:
        return {"success": False, "error": "Subscriber not found"}

    return {
        "success": True,
        "email": sub["email"],
        "status": sub.get("status", "active"),
        "categories": sub.get("categories", ALL_CATEGORIES),
        "all_categories": ALL_CATEGORIES,
    }


@router.post("/preferences")
async def update_preferences(req: PreferencesRequest):
    """Update subscriber category preferences."""
    expected = _make_token(req.email)
    if req.token != expected:
        return {"success": False, "error": "Invalid token"}

    valid_cats = [c for c in req.categories if c in ALL_CATEGORIES]
    result = await _db_mod.db.newsletter_subscribers.update_one(
        {"email": req.email.strip().lower()},
        {"$set": {"categories": valid_cats, "preferences_updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0 and result.matched_count == 0:
        return {"success": False, "error": "Subscriber not found"}

    return {"success": True, "message": "Preferences updated!", "categories": valid_cats}


def _unsubscribe_page(email: str, success: bool, error: str = "", already: bool = False) -> str:
    base_url = os.environ.get("FRONTEND_BASE_URL", "")
    token = _make_token(email)
    prefs_url = f"{base_url}/newsletter-preferences?email={email}&token={token}"

    if not success:
        body = f'<h1 style="color:#EF4444;font-size:24px;">Something went wrong</h1><p style="color:#64748B;font-size:15px;">{error}</p>'
    elif already:
        body = f'''
        <h1 style="color:#F8FAFC;font-size:24px;">Already Unsubscribed</h1>
        <p style="color:#94A3B8;font-size:15px;">This email was already unsubscribed.</p>
        <a href="{base_url}/blog" style="display:inline-block;margin-top:20px;background:#00D4AA;color:#0F172A;font-size:14px;font-weight:700;padding:12px 28px;border-radius:10px;text-decoration:none;">Visit Blog</a>
        '''
    else:
        body = f'''
        <h1 style="color:#F8FAFC;font-size:24px;">You've been unsubscribed</h1>
        <p style="color:#94A3B8;font-size:15px;line-height:1.6;">We're sorry to see you go. You won't receive any more emails from us.</p>
        <p style="color:#64748B;font-size:13px;margin-top:16px;">Changed your mind? You can always <a href="{prefs_url}" style="color:#00D4AA;">manage your preferences</a> or re-subscribe from the blog.</p>
        <a href="{base_url}/blog" style="display:inline-block;margin-top:20px;background:#1E293B;color:#F8FAFC;font-size:14px;font-weight:600;padding:12px 28px;border-radius:10px;text-decoration:none;border:1px solid #334155;">Visit Blog</a>
        '''

    return f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Unsubscribe - RealAICoach</title></head>
    <body style="margin:0;padding:0;background:#0F172A;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;">
      <div style="max-width:480px;margin:60px auto;text-align:center;padding:40px;">
        {body}
      </div>
    </body></html>
    """


def _build_digest_html(posts: list, subscriber_email: str, digest_id: str = "") -> str:
    """Build bi-weekly blog digest email HTML with tracking pixel and click-through links."""
    logo = render_email_logo("default")
    base_url = os.environ.get("FRONTEND_BASE_URL", os.environ.get("SSO_REDIRECT_BASE_URL", ""))
    token = _make_token(subscriber_email)
    unsub_url = f"{base_url}/api/newsletter/unsubscribe?email={subscriber_email}&token={token}"
    prefs_url = f"{base_url}/newsletter-preferences?email={subscriber_email}&token={token}"
    open_pixel = f"{base_url}/api/newsletter/track/open?d={digest_id}&e={subscriber_email}"

    posts_html = ""
    for p in posts[:5]:
        cat_colors = {
            'Industry Insights': '#3B82F6', 'Product Update': '#10B981', 'Tips & Tricks': '#F59E0B',
            'Research': '#8B5CF6', 'Company News': '#EC4899', 'Enterprise': '#06B6D4',
        }
        color = cat_colors.get(p.get('category', ''), '#3B82F6')
        raw_url = f"{base_url}/blog/{p['slug']}"
        post_url = f"{base_url}/api/newsletter/track/click?d={digest_id}&e={subscriber_email}&slug={p['slug']}&url={raw_url}"
        posts_html += f"""
        <tr><td style="padding-bottom:20px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="width:140px;vertical-align:top;">
                <img src="{p.get('image','')}" alt="{p.get('title','')}" style="width:140px;height:100px;object-fit:cover;" />
              </td>
              <td style="padding:14px 16px;vertical-align:top;">
                <span style="display:inline-block;background:{color}18;color:{color};font-size:10px;font-weight:700;padding:3px 8px;border-radius:8px;margin-bottom:6px;">{p.get('category','')}</span>
                <a href="{post_url}" style="display:block;color:#0F172A;font-size:15px;font-weight:700;text-decoration:none;line-height:1.3;margin-bottom:4px;">{p.get('title','')}</a>
                <span style="color:#64748B;font-size:12px;">{p.get('author','')} &middot; {p.get('read_time','')}</span>
              </td>
            </tr>
          </table>
        </td></tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:40px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">
        <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);padding:32px;text-align:center;">
          {logo}
          <h1 style="color:#F8FAFC;font-size:22px;font-weight:800;margin:14px 0 6px;">Your Bi-Weekly Blog Digest</h1>
          <p style="color:#94A3B8;font-size:13px;margin:0;">The latest insights in AI coaching and career development</p>
        </td></tr>
        <tr><td style="padding:28px 24px 8px;">
          <h2 style="color:#0F172A;font-size:16px;font-weight:700;margin:0 0 16px;">Latest Articles</h2>
          <table width="100%" cellpadding="0" cellspacing="0">
            {posts_html}
          </table>
        </td></tr>
        <tr><td style="padding:8px 24px 28px;text-align:center;">
          <a href="{base_url}/blog" style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:14px;font-weight:700;padding:12px 32px;border-radius:10px;text-decoration:none;">View All Articles</a>
        </td></tr>
        {_premium_mini_footer(reason="you subscribed to the RealAICoach blog digest",
                              show_unsub=True, prefs_url=prefs_url, unsub_url=unsub_url)}
      </table>
      <img src="{open_pixel}" width="1" height="1" style="display:none;" alt="" />
    </body>
    </html>
    """


async def send_blog_digest():
    """Send bi-weekly blog digest to blog-type subscribers only, filtered by category preferences."""
    from services.blog_service import get_blog_posts

    base_url = os.environ.get("FRONTEND_BASE_URL", os.environ.get("SSO_REDIRECT_BASE_URL", ""))

    subscribers = await _db_mod.db.newsletter_subscribers.find(
        {"status": "active", "subscription_type": {"$in": ["blog", "all"]}},
        {"_id": 0, "email": 1, "categories": 1}
    ).to_list(10000)

    if not subscribers:
        logger.info("No active newsletter subscribers for digest")
        return 0

    all_posts = await get_blog_posts(_db_mod.db)
    if not all_posts:
        logger.info("No active blog posts for digest")
        return 0

    digest_id = datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8]

    await _db_mod.db.newsletter_digests.insert_one({
        "digest_id": digest_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "total_recipients": 0,
        "post_slugs": [p["slug"] for p in all_posts[:5]],
    })

    sent = 0
    for sub in subscribers:
        sub_cats = sub.get("categories") or ALL_CATEGORIES
        filtered = [p for p in all_posts if p.get("category") in sub_cats][:5]
        if not filtered:
            continue

        _build_digest_html(filtered, sub["email"], digest_id)
        try:
            from utils.email_service import send_catalog_template
            result = await send_catalog_template(
                recipient_email=sub["email"],
                template_key="newsletter_blog_digest",
                posts=[{
                    "title": p.get("title", ""),
                    "category": p.get("category", ""),
                    "author": p.get("author", ""),
                    "read_time": p.get("read_time", ""),
                    "image": p.get("image", ""),
                    "url": f"{base_url}/api/newsletter/track/click?d={digest_id}&e={sub['email']}&slug={p['slug']}&url={base_url}/blog/{p['slug']}",
                } for p in filtered],
                unsub_url=f"{base_url}/api/newsletter/unsubscribe?email={sub['email']}&token={_make_token(sub['email'])}",
                prefs_url=f"{base_url}/newsletter-preferences?email={sub['email']}&token={_make_token(sub['email'])}",
                open_pixel_url=f"{base_url}/api/newsletter/track/open?d={digest_id}&e={sub['email']}",
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error") or "Email send failed"))
            sent += 1
        except Exception as e:
            logger.warning(f"Digest send failed for {sub['email']}: {e}")

    await _db_mod.db.newsletter_digests.update_one(
        {"digest_id": digest_id}, {"$set": {"total_recipients": sent}}
    )
    logger.info(f"Blog digest sent to {sent}/{len(subscribers)} subscribers (digest_id={digest_id})")
    return sent


@router.post("/trigger-digest")
async def trigger_blog_digest():
    """Manually trigger the bi-weekly blog digest (admin/test use)."""
    try:
        sent = await send_blog_digest()
        return {"success": True, "sent": sent}
    except Exception as e:
        logger.error(f"Manual digest trigger failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/trigger-weekly")
async def trigger_weekly_newsletter():
    """Manually trigger the weekly platform newsletter (admin/test use)."""
    try:
        sent = await send_weekly_newsletter()
        return {"success": True, "sent": sent, "type": "weekly_newsletter"}
    except Exception as e:
        logger.error(f"Manual weekly newsletter trigger failed: {e}")
        return {"success": False, "error": str(e)}


# ── Tracking Endpoints ──

PIXEL_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


@router.get("/track/open")
async def track_open(d: str = Query(""), e: str = Query("")):
    """Track email open via invisible pixel."""
    if d and e:
        await _db_mod.db.newsletter_events.insert_one({
            "type": "open",
            "digest_id": d,
            "email": e.lower(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    return Response(content=PIXEL_GIF, media_type="image/gif", headers={"Cache-Control": "no-store, no-cache"})


@router.get("/track/click")
async def track_click(
    d: str = Query(""), e: str = Query(""), slug: str = Query(""), url: str = Query("")
):
    """Track link click and redirect to target URL."""
    if d and e:
        await _db_mod.db.newsletter_events.insert_one({
            "type": "click",
            "digest_id": d,
            "email": e.lower(),
            "slug": slug,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    target = url or os.environ.get("FRONTEND_BASE_URL", "/")
    return RedirectResponse(url=target, status_code=302)


# ── Analytics Endpoints ──

@router.get("/analytics")
async def get_newsletter_analytics():
    """Get newsletter analytics for admin dashboard."""
    now = datetime.now(timezone.utc)

    total_subs = await _db_mod.db.newsletter_subscribers.count_documents({})
    active_subs = await _db_mod.db.newsletter_subscribers.count_documents({"status": "active"})
    unsub_count = await _db_mod.db.newsletter_subscribers.count_documents({"status": "unsubscribed"})

    sub_sources = await _db_mod.db.newsletter_subscribers.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}}
    ]).to_list(20)

    digests = await _db_mod.db.newsletter_digests.find(
        {}, {"_id": 0}
    ).sort("sent_at", -1).to_list(20)

    total_opens = await _db_mod.db.newsletter_events.count_documents({"type": "open"})
    total_clicks = await _db_mod.db.newsletter_events.count_documents({"type": "click"})

    unique_openers = len(await _db_mod.db.newsletter_events.distinct("email", {"type": "open"}))
    unique_clickers = len(await _db_mod.db.newsletter_events.distinct("email", {"type": "click"}))

    top_articles = await _db_mod.db.newsletter_events.aggregate([
        {"$match": {"type": "click", "slug": {"$exists": True, "$ne": ""}}},
        {"$group": {"_id": "$slug", "clicks": {"$sum": 1}, "unique_emails": {"$addToSet": "$email"}}},
        {"$project": {"slug": "$_id", "clicks": 1, "unique_readers": {"$size": "$unique_emails"}, "_id": 0}},
        {"$sort": {"clicks": -1}},
        {"$limit": 10},
    ]).to_list(10)

    opens_by_digest = await _db_mod.db.newsletter_events.aggregate([
        {"$match": {"type": "open"}},
        {"$group": {"_id": "$digest_id", "opens": {"$sum": 1}, "unique": {"$addToSet": "$email"}}},
        {"$project": {"digest_id": "$_id", "opens": 1, "unique_opens": {"$size": "$unique"}, "_id": 0}},
        {"$sort": {"digest_id": -1}},
        {"$limit": 20},
    ]).to_list(20)

    clicks_by_digest = await _db_mod.db.newsletter_events.aggregate([
        {"$match": {"type": "click"}},
        {"$group": {"_id": "$digest_id", "clicks": {"$sum": 1}, "unique": {"$addToSet": "$email"}}},
        {"$project": {"digest_id": "$_id", "clicks": 1, "unique_clicks": {"$size": "$unique"}, "_id": 0}},
        {"$sort": {"digest_id": -1}},
        {"$limit": 20},
    ]).to_list(20)

    last_30d_subs = await _db_mod.db.newsletter_subscribers.count_documents({
        "subscribed_at": {"$gte": (now - timedelta(days=30)).isoformat()}
    })

    cat_prefs = await _db_mod.db.newsletter_subscribers.aggregate([
        {"$match": {"status": "active", "categories": {"$exists": True}}},
        {"$unwind": "$categories"},
        {"$group": {"_id": "$categories", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(10)

    return {
        "subscribers": {
            "total": total_subs,
            "active": active_subs,
            "unsubscribed": unsub_count,
            "last_30d": last_30d_subs,
            "sources": {s["_id"]: s["count"] for s in sub_sources if s["_id"]},
        },
        "engagement": {
            "total_opens": total_opens,
            "total_clicks": total_clicks,
            "unique_openers": unique_openers,
            "unique_clickers": unique_clickers,
            "open_rate": round(unique_openers / active_subs * 100, 1) if active_subs else 0,
            "click_rate": round(unique_clickers / active_subs * 100, 1) if active_subs else 0,
        },
        "top_articles": top_articles,
        "digests": digests,
        "opens_by_digest": opens_by_digest,
        "clicks_by_digest": clicks_by_digest,
        "category_preferences": {c["_id"]: c["count"] for c in cat_prefs if c["_id"]},
    }



@router.get("/subscriber-growth")
async def get_subscriber_growth():
    """Enhanced subscriber growth analytics with type breakdown and time series."""
    now = datetime.now(timezone.utc)

    # Subscriber counts by type
    type_counts = await _db_mod.db.newsletter_subscribers.aggregate([
        {"$group": {"_id": "$subscription_type", "total": {"$sum": 1},
                     "active": {"$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}},
                     "unsubscribed": {"$sum": {"$cond": [{"$eq": ["$status", "unsubscribed"]}, 1, 0]}}}}
    ]).to_list(10)
    by_type = {}
    for t in type_counts:
        key = t["_id"] or "unknown"
        by_type[key] = {"total": t["total"], "active": t["active"], "unsubscribed": t["unsubscribed"]}

    # Daily subscriber growth (last 30 days)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    daily_growth = await _db_mod.db.newsletter_subscribers.aggregate([
        {"$match": {"subscribed_at": {"$gte": thirty_days_ago}}},
        {"$addFields": {"day": {"$substr": ["$subscribed_at", 0, 10]}}},
        {"$group": {"_id": {"day": "$day", "type": {"$ifNull": ["$subscription_type", "platform"]}},
                     "count": {"$sum": 1}}},
        {"$sort": {"_id.day": 1}},
    ]).to_list(200)
    growth_series = {}
    for g in daily_growth:
        day = g["_id"]["day"]
        stype = g["_id"]["type"]
        if day not in growth_series:
            growth_series[day] = {"date": day, "platform": 0, "blog": 0, "all": 0}
        growth_series[day][stype] = g["count"]
    growth_timeline = sorted(growth_series.values(), key=lambda x: x["date"])

    # Campaign performance (newsletter_digests with engagement)
    campaigns = await _db_mod.db.newsletter_digests.find(
        {}, {"_id": 0}
    ).sort("sent_at", -1).to_list(20)

    campaign_stats = []
    for c in campaigns:
        did = c.get("digest_id", "")
        opens = await _db_mod.db.newsletter_events.count_documents({"type": "open", "digest_id": did})
        unique_opens = len(await _db_mod.db.newsletter_events.distinct("email", {"type": "open", "digest_id": did}))
        clicks = await _db_mod.db.newsletter_events.count_documents({"type": "click", "digest_id": did})
        unique_clicks = len(await _db_mod.db.newsletter_events.distinct("email", {"type": "click", "digest_id": did}))
        total = c.get("total_recipients", 0)
        campaign_stats.append({
            "digest_id": did,
            "type": c.get("type", "blog_digest"),
            "sent_at": c.get("sent_at", ""),
            "total_recipients": total,
            "opens": opens,
            "unique_opens": unique_opens,
            "clicks": clicks,
            "unique_clicks": unique_clicks,
            "open_rate": round(unique_opens / total * 100, 1) if total else 0,
            "click_rate": round(unique_clicks / total * 100, 1) if total else 0,
        })

    # Top clicked content
    top_content = await _db_mod.db.newsletter_events.aggregate([
        {"$match": {"type": "click", "slug": {"$exists": True, "$ne": ""}}},
        {"$group": {"_id": "$slug", "clicks": {"$sum": 1}, "emails": {"$addToSet": "$email"}}},
        {"$project": {"slug": "$_id", "clicks": 1, "unique_readers": {"$size": "$emails"}, "_id": 0}},
        {"$sort": {"clicks": -1}},
        {"$limit": 10},
    ]).to_list(10)

    # Unsubscribe trend (last 30 days)
    unsub_events = await _db_mod.db.newsletter_subscribers.aggregate([
        {"$match": {"status": "unsubscribed", "unsubscribed_at": {"$exists": True, "$gte": thirty_days_ago}}},
        {"$addFields": {"day": {"$substr": ["$unsubscribed_at", 0, 10]}}},
        {"$group": {"_id": "$day", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]).to_list(30)

    # Summary stats
    total_active = await _db_mod.db.newsletter_subscribers.count_documents({"status": "active"})
    total_all = await _db_mod.db.newsletter_subscribers.count_documents({})
    this_week = (now - timedelta(days=7)).isoformat()
    new_this_week = await _db_mod.db.newsletter_subscribers.count_documents({"subscribed_at": {"$gte": this_week}})
    unsub_this_week = await _db_mod.db.newsletter_subscribers.count_documents({
        "status": "unsubscribed", "unsubscribed_at": {"$gte": this_week}
    })

    return {
        "summary": {
            "total_subscribers": total_all,
            "active_subscribers": total_active,
            "new_this_week": new_this_week,
            "unsubscribed_this_week": unsub_this_week,
            "growth_rate": round(new_this_week / total_all * 100, 1) if total_all else 0,
            "churn_rate": round(unsub_this_week / total_active * 100, 1) if total_active else 0,
        },
        "by_type": by_type,
        "growth_timeline": growth_timeline,
        "campaigns": campaign_stats,
        "top_content": top_content,
        "unsubscribe_trend": [{"date": u["_id"], "count": u["count"]} for u in unsub_events],
    }

HERO_IMG = "https://images.unsplash.com/photo-1580894732930-0babd100d356?w=1200&h=400&fit=crop&crop=faces"
TEAM_IMG = "https://images.unsplash.com/photo-1769740333462-9a63bfa914bc?w=600&h=300&fit=crop"
GLOBAL_IMG = "https://images.unsplash.com/photo-1583054346111-3ceb09bbf9eb?w=600&h=300&fit=crop"


async def _get_weekly_newsletter_payload() -> dict:
    gps = await _db_mod.db.global_platform_state.find_one(
        {"state_id": "global-platform-state"},
        {"_id": 0, "features": 1, "messaging": 1, "meta": 1},
    )
    features = [item for item in (gps or {}).get("features", []) if item.get("enabled", True)]
    live_features = [item for item in features if str(item.get("status") or "active").lower() not in {"planned", "upcoming", "coming_soon"}]
    coming_features = [item for item in features if str(item.get("status") or "").lower() in {"planned", "upcoming", "coming_soon"}]
    weekly_features = [
        {
            "title": str(item.get("title") or item.get("feature_id") or ""),
            "desc": str(item.get("description") or ""),
            "icon": str(item.get("icon") or "&#10024;"),
            "color": str(item.get("color") or "#14B8A6"),
            "status": str(item.get("status") or "Live"),
        }
        for item in live_features[:4]
    ]
    coming_soon = [
        {
            "title": str(item.get("title") or item.get("feature_id") or ""),
            "desc": str(item.get("description") or ""),
            "color": str(item.get("color") or "#14B8A6"),
        }
        for item in coming_features[:4]
    ]
    messaging = (gps or {}).get("messaging") or {}
    testimonials = [item for item in messaging.get("testimonials", []) if isinstance(item, dict)]
    counts = ((gps or {}).get("meta") or {}).get("counts") or {}
    impact_stats = [
        {"value": str(counts.get("features", 0)), "label": "Features", "color": "#14B8A6"},
        {"value": str(counts.get("plans", 0)), "label": "Plans", "color": "#10B981"},
        {"value": str(counts.get("faq", 0)), "label": "FAQ", "color": "#F59E0B"},
        {"value": str(counts.get("knowledge_docs", 0)), "label": "Knowledge", "color": "#0F766E"},
    ]
    return {"features": weekly_features, "coming_soon": coming_soon, "testimonials": testimonials, "impact_stats": impact_stats}


def _build_weekly_newsletter_html(subscriber_email: str, payload: dict) -> str:
    base_url = os.environ.get("FRONTEND_BASE_URL", "")
    token = _make_token(subscriber_email)
    unsub_url = f"{base_url}/api/newsletter/unsubscribe?email={subscriber_email}&token={token}"
    prefs_url = f"{base_url}/newsletter-preferences?email={subscriber_email}&token={token}"
    signup_url = f"{base_url}/auth/register"
    newsletter_id = f"weekly-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    open_pixel = f"{base_url}/api/newsletter/track/open?d={newsletter_id}&e={subscriber_email}"

    week_date = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # Features HTML
    features_html = ""
    for f in payload.get("features", []):
        features_html += f"""
        <tr><td style="padding-bottom:16px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;overflow:hidden;">
            <tr><td style="padding:18px 20px;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:44px;vertical-align:top;">
                  <div style="width:40px;height:40px;border-radius:10px;background:{f['color']}15;text-align:center;line-height:40px;font-size:20px;">{f['icon']}</div>
                </td>
                <td style="padding-left:14px;vertical-align:top;">
                  <table cellpadding="0" cellspacing="0"><tr>
                    <td><span style="color:#0F172A;font-size:15px;font-weight:700;">{f['title']}</span></td>
                    <td style="padding-left:8px;"><span style="display:inline-block;background:{f['color']}18;color:{f['color']};font-size:9px;font-weight:800;padding:3px 8px;border-radius:10px;letter-spacing:0.5px;">{f['status']}</span></td>
                  </tr></table>
                  <p style="color:#64748B;font-size:13px;line-height:1.5;margin:6px 0 0;">{f['desc']}</p>
                </td>
              </tr></table>
            </td></tr>
          </table>
        </td></tr>"""

    # Coming Soon HTML
    coming_html = ""
    for c in payload.get("coming_soon", []):
        coming_html += f"""
        <tr><td style="padding-bottom:10px;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:8px;"><div style="width:6px;height:6px;border-radius:3px;background:{c['color']};"></div></td>
            <td style="padding-left:10px;">
              <span style="color:#0F172A;font-size:14px;font-weight:600;">{c['title']}</span>
              <span style="color:#64748B;font-size:12px;"> — {c['desc']}</span>
            </td>
          </tr></table>
        </td></tr>"""

    # Testimonials HTML
    testimonials_html = ""
    for t in payload.get("testimonials", []):
        stars = "".join('<span style="color:#F59E0B;font-size:14px;">&#9733;</span>' for _ in range(int(t.get("stars") or 5)))
        name = str(t.get("name") or "")
        initial = name[:1]
        testimonials_html += f"""
        <tr><td style="padding-bottom:16px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:12px;overflow:hidden;">
            <tr><td style="padding:20px;">
              <div style="margin-bottom:12px;">{stars}</div>
              <p style="color:#334155;font-size:14px;line-height:1.6;margin:0 0 14px;font-style:italic;">"{t.get('text', '')}"</p>
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;">
                  <div style="width:32px;height:32px;border-radius:16px;background:{t.get('avatar_color', '#14B8A6')};text-align:center;line-height:32px;color:#FFF;font-size:14px;font-weight:700;">{initial}</div>
                </td>
                <td style="padding-left:10px;">
                  <span style="color:#0F172A;font-size:13px;font-weight:700;">{name}</span><br>
                  <span style="color:#64748B;font-size:11px;">{t.get('title', '')}</span>
                </td>
              </tr></table>
            </td></tr>
          </table>
        </td></tr>"""

    # Impact Stats HTML
    stats_html = ""
    for s in payload.get("impact_stats", []):
        stats_html += f"""
        <td style="text-align:center;padding:16px 8px;">
          <div style="color:{s['color']};font-size:24px;font-weight:900;letter-spacing:-0.5px;">{s['value']}</div>
          <div style="color:#64748B;font-size:11px;font-weight:600;margin-top:4px;">{s['label']}</div>
        </td>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RealAICoach Weekly</title></head>
<body style="margin:0;padding:0;background:#E2E8F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:24px auto;background:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.08);">

    <!-- HERO HEADER -->
    <tr><td>
      <table width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(145deg,#0F172A 0%,#1E293B 100%);">
        <tr><td style="padding:0;">
          <img src="{HERO_IMG}" alt="RealAICoach" style="width:100%;height:220px;object-fit:cover;display:block;opacity:0.3;" />
          <div style="margin-top:-180px;position:relative;padding:20px 32px 40px;text-align:center;">
            <div style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:10px;font-weight:800;padding:5px 14px;border-radius:20px;letter-spacing:1px;margin-bottom:14px;">WEEKLY NEWSLETTER</div>
            <h1 style="color:#F8FAFC;font-size:28px;font-weight:900;margin:10px 0 8px;letter-spacing:-0.5px;line-height:1.2;">Your Week in AI Coaching</h1>
            <p style="color:#94A3B8;font-size:14px;margin:0;line-height:1.6;">Features, insights, and what's next at RealAICoach</p>
            <p style="color:#64748B;font-size:12px;margin:10px 0 0;">{week_date}</p>
          </div>
        </td></tr>
      </table>
    </td></tr>

    <!-- WHAT'S NEW -->
    <tr><td style="padding:32px 28px 8px;">
      <table cellpadding="0" cellspacing="0"><tr>
        <td style="width:4px;background:linear-gradient(180deg,#00D4AA,#3B82F6);border-radius:2px;"></td>
        <td style="padding-left:14px;">
          <h2 style="color:#0F172A;font-size:20px;font-weight:800;margin:0;letter-spacing:-0.3px;">Platform Highlights</h2>
          <p style="color:#64748B;font-size:13px;margin:4px 0 0;">What's powering your growth this week</p>
        </td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:16px 28px 8px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        {features_html}
      </table>
    </td></tr>

    <!-- CTA #1 -->
    <tr><td style="padding:16px 28px 32px;text-align:center;">
      <a href="{signup_url}" style="display:inline-block;background:linear-gradient(135deg,#00D4AA 0%,#00B4D8 100%);color:#0F172A;font-size:16px;font-weight:800;text-decoration:none;padding:16px 44px;border-radius:12px;letter-spacing:-0.2px;box-shadow:0 4px 16px rgba(0,212,170,0.3);">
        Start Your Free Journey
      </a>
      <p style="color:#94A3B8;font-size:12px;margin:10px 0 0;">No credit card required. live AI tools ready to use.</p>
    </td></tr>

    <!-- COMING SOON -->
    <tr><td style="background:#F8FAFC;padding:28px;border-top:1px solid #E2E8F0;border-bottom:1px solid #E2E8F0;">
      <h2 style="color:#0F172A;font-size:18px;font-weight:800;margin:0 0 4px;">Coming Soon</h2>
      <p style="color:#64748B;font-size:13px;margin:0 0 16px;">What's on our roadmap</p>
      <table width="100%" cellpadding="0" cellspacing="0">
        {coming_html}
      </table>
    </td></tr>

    <!-- GLOBAL IMPACT -->
    <tr><td style="padding:28px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td colspan="4">
          <img src="{GLOBAL_IMG}" alt="Global Impact" style="width:100%;height:160px;object-fit:cover;border-radius:14px;display:block;margin-bottom:20px;" />
          <h2 style="color:#0F172A;font-size:18px;font-weight:800;margin:0 0 4px;">Worldwide Impact</h2>
          <p style="color:#64748B;font-size:13px;margin:0 0 16px;">Empowering individuals and teams across the globe</p>
        </td></tr>
        <tr>{stats_html}</tr>
      </table>
    </td></tr>

    <!-- TESTIMONIALS -->
    <tr><td style="background:#F8FAFC;padding:28px;border-top:1px solid #E2E8F0;border-bottom:1px solid #E2E8F0;">
      <h2 style="color:#0F172A;font-size:18px;font-weight:800;margin:0 0 4px;">What Our Users Say</h2>
      <p style="color:#64748B;font-size:13px;margin:0 0 16px;">Real stories from real professionals</p>
      <table width="100%" cellpadding="0" cellspacing="0">
        {testimonials_html}
      </table>
    </td></tr>

    <!-- TEAM SECTION -->
    <tr><td style="padding:28px;">
      <img src="{TEAM_IMG}" alt="Our Team" style="width:100%;height:180px;object-fit:cover;border-radius:14px;display:block;margin-bottom:20px;" />
      <h2 style="color:#0F172A;font-size:18px;font-weight:800;margin:0 0 16px;">From Our Team</h2>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="width:50%;padding-right:8px;vertical-align:top;">
            <table cellpadding="0" cellspacing="0"><tr>
              <td style="width:36px;vertical-align:top;">
                <div style="width:32px;height:32px;border-radius:16px;background:#0F172A;text-align:center;line-height:32px;color:#00D4AA;font-size:14px;font-weight:700;">A</div>
              </td>
              <td style="padding-left:10px;">
                <span style="color:#0F172A;font-size:13px;font-weight:700;">Alex Chen</span><br>
                <span style="color:#64748B;font-size:11px;">CEO & Co-Founder</span>
              </td>
            </tr></table>
          </td>
          <td style="width:50%;padding-left:8px;vertical-align:top;">
            <table cellpadding="0" cellspacing="0"><tr>
              <td style="width:36px;vertical-align:top;">
                <div style="width:32px;height:32px;border-radius:16px;background:#0F172A;text-align:center;line-height:32px;color:#3B82F6;font-size:14px;font-weight:700;">M</div>
              </td>
              <td style="padding-left:10px;">
                <span style="color:#0F172A;font-size:13px;font-weight:700;">Maria Santos</span><br>
                <span style="color:#64748B;font-size:11px;">CTO & Co-Founder</span>
              </td>
            </tr></table>
          </td>
        </tr>
        <tr><td colspan="2" style="padding-top:12px;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:36px;vertical-align:top;">
              <div style="width:32px;height:32px;border-radius:16px;background:#0F172A;text-align:center;line-height:32px;color:#F59E0B;font-size:14px;font-weight:700;">D</div>
            </td>
            <td style="padding-left:10px;">
              <span style="color:#0F172A;font-size:13px;font-weight:700;">Dr. David Park</span><br>
              <span style="color:#64748B;font-size:11px;">Head of AI Research</span>
            </td>
          </tr></table>
        </td></tr>
      </table>
      <p style="color:#64748B;font-size:13px;line-height:1.6;margin:16px 0 0;font-style:italic;">
        "We started RealAICoach with a simple belief: everyone deserves access to world-class coaching. This week, we're one step closer with new features that make AI coaching more personal, more insightful, and more accessible than ever. Thank you for being part of this journey."
      </p>
      <p style="color:#0F172A;font-size:13px;font-weight:700;margin:10px 0 0;">— The RealAICoach Leadership Team</p>
    </td></tr>

    <!-- FINAL CTA -->
    <tr><td style="background:linear-gradient(145deg,#0F172A 0%,#1E293B 100%);padding:36px 28px;text-align:center;">
      <h2 style="color:#F8FAFC;font-size:22px;font-weight:800;margin:0 0 8px;">Ready to Transform Your Growth?</h2>
      <p style="color:#94A3B8;font-size:14px;margin:0 0 24px;line-height:1.6;">Join 150,000+ professionals using AI to unlock their full potential.</p>
      <a href="{signup_url}" style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:16px;font-weight:800;text-decoration:none;padding:16px 48px;border-radius:12px;letter-spacing:-0.2px;">
        Create Your Free Account
      </a>
    </td></tr>

    <!-- FOOTER -->
    {_premium_mini_footer(subscriber_email, reason=f"{subscriber_email} subscribed to the RealAICoach newsletter",
                          show_unsub=True, prefs_url=prefs_url, unsub_url=unsub_url)}

  </table>
  <img src="{open_pixel}" width="1" height="1" style="display:none;" alt="" />
</body></html>"""


async def send_weekly_newsletter():
    """Send weekly platform newsletter to platform-type subscribers only. Fully automated."""
    base_url = os.environ.get("FRONTEND_BASE_URL", os.environ.get("SSO_REDIRECT_BASE_URL", ""))

    subscribers = []
    async for row in iter_find_paginated(
        _db_mod.db.newsletter_subscribers,
        {"status": "active", "subscription_type": {"$in": ["platform", "all"]}},
        {"_id": 0, "email": 1},
        page_size=1000,
        max_docs=50000,
    ):
        subscribers.append(row)

    if not subscribers:
        logger.info("No active subscribers for weekly newsletter")
        return 0

    newsletter_id = f"weekly-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    # Check if already sent this week
    existing = await _db_mod.db.newsletter_digests.find_one({"digest_id": newsletter_id})
    if existing:
        logger.info(f"Weekly newsletter {newsletter_id} already sent")
        return 0

    await _db_mod.db.newsletter_digests.insert_one({
        "digest_id": newsletter_id,
        "type": "weekly_newsletter",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "total_recipients": 0,
    })

    sent = 0
    newsletter_payload = await _get_weekly_newsletter_payload()
    for sub in subscribers:
        _build_weekly_newsletter_html(sub["email"], newsletter_payload)
        try:
            from utils.email_service import send_catalog_template
            token = _make_token(sub["email"])
            result = await send_catalog_template(
                recipient_email=sub["email"],
                template_key="newsletter_weekly",
                features=newsletter_payload["features"],
                coming_soon=newsletter_payload["coming_soon"],
                testimonials=newsletter_payload["testimonials"],
                impact_stats=newsletter_payload["impact_stats"],
                week_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
                signup_url=f"{base_url}/auth/register",
                unsub_url=f"{base_url}/api/newsletter/unsubscribe?email={sub['email']}&token={token}",
                prefs_url=f"{base_url}/newsletter-preferences?email={sub['email']}&token={token}",
                open_pixel_url=f"{base_url}/api/newsletter/track/open?d=weekly-{datetime.now(timezone.utc).strftime('%Y%m%d')}&e={sub['email']}",
            )
            if not result.get("success"):
                raise RuntimeError(str(result.get("error") or "Email send failed"))
            sent += 1
        except Exception as e:
            logger.warning(f"Weekly newsletter failed for {sub['email']}: {e}")

    await _db_mod.db.newsletter_digests.update_one(
        {"digest_id": newsletter_id}, {"$set": {"total_recipients": sent}}
    )
    logger.info(f"Weekly newsletter sent to {sent}/{len(subscribers)} subscribers")
    return sent



async def send_tz_aware_briefings_due(now_utc: Optional[datetime] = None, only_email: Optional[str] = None) -> dict:
    """Dispatch the weekly briefing to every subscriber whose preferred
    ``(weekday, hour)`` matches the current time **in their own timezone**.

    Designed to be called every 15 minutes by the APScheduler cron. Uses
    a per-subscriber-per-ISO-week idempotency key in
    ``newsletter_digests`` so a single subscriber cannot receive more
    than one briefing per week even if the scheduler fires multiple
    times during the matching hour window.

    Returns a summary dict:
        {
          "checked": N,       # subscribers evaluated
          "matched": N,       # subscribers whose local (wd, hour) matched now
          "sent": N,          # actually dispatched this tick
          "skipped_dedup": N, # already received this week
          "failed": N,
        }
    """
    base_url = os.environ.get(
        "FRONTEND_BASE_URL", os.environ.get("SSO_REDIRECT_BASE_URL", "")
    )
    now = (now_utc or datetime.now(timezone.utc))

    query = {
        "status": "active",
        "subscription_type": {"$in": ["platform", "all"]},
    }
    if only_email:
        query["email"] = only_email.lower().strip()

    summary = {"checked": 0, "matched": 0, "sent": 0, "skipped_dedup": 0, "failed": 0}
    cursor = _db_mod.db.newsletter_subscribers.find(
        query,
        {
            "_id": 0, "email": 1, "timezone": 1,
            "preferred_weekday": 1, "preferred_hour": 1,
        },
    )
    async for sub in cursor:
        summary["checked"] += 1
        tz_name = sub.get("timezone")
        if not tz_name:
            continue
        try:
            tz = ZoneInfo(str(tz_name))
        except (ZoneInfoNotFoundError, Exception):
            continue
        local = now.astimezone(tz)
        wd = int(sub.get("preferred_weekday") or _BRIEFING_WEEKDAY)
        hr = int(sub.get("preferred_hour") or _BRIEFING_HOUR)
        if not (local.weekday() == wd and local.hour == hr):
            continue
        summary["matched"] += 1

        # Idempotency: one briefing per subscriber per ISO week (in their TZ).
        iso_year, iso_week, _ = local.isocalendar()
        dedup_key = f"tz-briefing:{sub['email']}:{iso_year}-W{iso_week:02d}"
        already = await _db_mod.db.newsletter_digests.find_one({"digest_id": dedup_key})
        if already:
            summary["skipped_dedup"] += 1
            continue

        # Subject-line A/B pick (stable per (email, iso-week)).
        ab = _pick_subject_variant(sub["email"], iso_year, iso_week, local.hour)

        # Reserve the dedup slot BEFORE sending to prevent double-send on
        # concurrent scheduler ticks across replicas.
        try:
            await _db_mod.db.newsletter_digests.insert_one(
                {
                    "digest_id": dedup_key,
                    "type": "tz_aware_weekly_briefing",
                    "email": sub["email"],
                    "timezone": tz_name,
                    "weekday": wd,
                    "hour": hr,
                    "subject_variant": ab["variant"],
                    "subject_bucket": ab["bucket"],
                    "subject": ab["subject"],
                    "sent_at": now.isoformat(),
                    "status": "reserved",
                }
            )
        except Exception:
            # Duplicate-key race from another replica — another worker
            # is handling this subscriber; skip.
            summary["skipped_dedup"] += 1
            continue

        try:
            from utils.email_service import send_catalog_template
            token = _make_token(sub["email"])
            newsletter_payload = await _get_weekly_newsletter_payload()
            res = await send_catalog_template(
                recipient_email=sub["email"],
                template_key="newsletter_weekly",
                subject_override=ab["subject"],
                features=newsletter_payload["features"],
                coming_soon=newsletter_payload["coming_soon"],
                testimonials=newsletter_payload["testimonials"],
                impact_stats=newsletter_payload["impact_stats"],
                week_date=local.strftime("%B %d, %Y"),
                signup_url=f"{base_url}/auth/register",
                unsub_url=f"{base_url}/api/newsletter/unsubscribe?email={sub['email']}&token={token}",
                prefs_url=f"{base_url}/newsletter-preferences?email={sub['email']}&token={token}",
                open_pixel_url=f"{base_url}/api/newsletter/track/open?d={dedup_key}&e={sub['email']}",
            )
            if not res.get("success"):
                raise RuntimeError(str(res.get("error") or "send failed"))
            summary["sent"] += 1
            await _db_mod.db.newsletter_digests.update_one(
                {"digest_id": dedup_key},
                {"$set": {"status": "sent", "message_id": res.get("message_id") or ""}},
            )
        except Exception as exc:
            summary["failed"] += 1
            logger.warning(
                f"[tz-briefing] dispatch failed for {sub['email']} "
                f"({tz_name} wd={wd} h={hr}): {exc}"
            )
            # Release the dedup reservation so the next scheduler tick
            # inside the same hour window can retry.
            try:
                await _db_mod.db.newsletter_digests.delete_one({"digest_id": dedup_key})
            except Exception:
                pass

    return summary


@router.post("/admin/dispatch-due-now")
async def admin_dispatch_due_now(only_email: Optional[str] = Query(None)):
    """Manually fire the TZ-aware dispatcher (admin test + CI hook)."""
    return await send_tz_aware_briefings_due(only_email=only_email)


@router.get("/ab/subject-performance")
async def ab_subject_performance():
    """A/B-test performance for the TZ-aware weekly briefing subject line.

    Joins ``newsletter_digests`` (type=tz_aware_weekly_briefing) against
    ``newsletter_events`` (type=open) on ``digest_id`` to produce an
    open-rate breakdown by (hour_bucket, variant) plus overall totals.
    """
    return await _compute_ab_performance()


async def _compute_ab_performance() -> dict:
    """Internal helper used by both the public endpoint and auto-promote."""
    digests = []
    async for row in iter_find_paginated(
        _db_mod.db.newsletter_digests,
        {"type": "tz_aware_weekly_briefing"},
        {
            "_id": 0,
            "digest_id": 1,
            "email": 1,
            "subject_variant": 1,
            "subject_bucket": 1,
            "subject": 1,
            "status": 1,
        },
        page_size=1000,
        max_docs=50000,
    ):
        digests.append(row)

    opened_ids: set[str] = set(
        await _db_mod.db.newsletter_events.distinct(
            "digest_id",
            {"type": "open", "digest_id": {"$regex": "^tz-briefing:"}},
        )
    )

    buckets: dict[str, dict[str, dict[str, int]]] = {}
    overall = {
        "A": {"sent": 0, "opened": 0},
        "B": {"sent": 0, "opened": 0},
    }
    for d in digests:
        if d.get("status") != "sent":
            continue
        variant = d.get("subject_variant") or "A"
        bucket = d.get("subject_bucket") or "unknown"
        if variant not in ("A", "B"):
            variant = "A"
        slot = buckets.setdefault(bucket, {
            "A": {"sent": 0, "opened": 0, "subject": _SUBJECT_AB_VARIANTS.get(bucket, {}).get("A", "")},
            "B": {"sent": 0, "opened": 0, "subject": _SUBJECT_AB_VARIANTS.get(bucket, {}).get("B", "")},
        })
        slot[variant]["sent"] += 1
        overall[variant]["sent"] += 1
        if d["digest_id"] in opened_ids:
            slot[variant]["opened"] += 1
            overall[variant]["opened"] += 1

    def _rate(slot: dict) -> float:
        return round(slot["opened"] / slot["sent"] * 100, 1) if slot["sent"] else 0.0

    out_buckets = []
    for bucket_name in ("morning", "afternoon", "evening", "night"):
        if bucket_name not in buckets:
            continue
        slot = buckets[bucket_name]
        a_rate = _rate(slot["A"])
        b_rate = _rate(slot["B"])
        winner = "A" if a_rate > b_rate else ("B" if b_rate > a_rate else "tie")
        out_buckets.append({
            "bucket": bucket_name,
            "A": {**slot["A"], "open_rate": a_rate},
            "B": {**slot["B"], "open_rate": b_rate},
            "winner": winner,
            "total_sent": slot["A"]["sent"] + slot["B"]["sent"],
        })

    total_a_rate = _rate(overall["A"])
    total_b_rate = _rate(overall["B"])
    return {
        "buckets": out_buckets,
        "overall": {
            "A": {**overall["A"], "open_rate": total_a_rate},
            "B": {**overall["B"], "open_rate": total_b_rate},
            "winner": "A" if total_a_rate > total_b_rate else ("B" if total_b_rate > total_a_rate else "tie"),
        },
        "variants": _SUBJECT_AB_VARIANTS,
        "frozen_winners": dict(_FROZEN_WINNERS),
    }


# ── Admin: promote / revert A/B winners ───────────────────────────────

_VALID_BUCKETS = ("morning", "afternoon", "evening", "night")


async def _load_frozen_winners_from_db() -> dict[str, str]:
    """Refresh the in-process ``_FROZEN_WINNERS`` cache from Mongo.

    Called on import (best-effort) and after every promote/revert call so
    the cache and DB never disagree across backend workers.
    """
    out: dict[str, str] = {}
    try:
        async for doc in _db_mod.db.newsletter_ab_winners.find(
            {}, {"_id": 0, "bucket": 1, "variant": 1}
        ):
            bucket = doc.get("bucket")
            variant = doc.get("variant")
            if bucket in _VALID_BUCKETS and variant in ("A", "B"):
                out[bucket] = variant
    except Exception as exc:
        logger.warning(f"[newsletter-ab] winner cache reload failed: {exc}")
    _FROZEN_WINNERS.clear()
    _FROZEN_WINNERS.update(out)
    return out


class PromoteWinnerBody(BaseModel):
    bucket: str = Field(..., description="morning|afternoon|evening|night")
    variant: str | None = Field(
        None, description="'A' or 'B'. Required when mode='manual' (default).",
    )
    mode: str = Field(
        "manual",
        description="'manual' uses the provided variant; 'auto' picks the winner by lift + min-sample guard.",
    )
    min_samples: int = Field(
        100,
        description="Minimum sent count PER variant required before auto-promotion can fire.",
        ge=1,
    )
    min_lift_pct: float = Field(
        2.0,
        description="Minimum absolute open-rate lift (in percentage points) the leader must beat the loser by.",
        ge=0,
    )


class RevertWinnerBody(BaseModel):
    bucket: str = Field(..., description="morning|afternoon|evening|night")


@router.post("/ab/promote-winner")
async def promote_ab_winner(body: PromoteWinnerBody, request: Request):
    """Freeze the winning variant for a bucket (admin-only).

    Two modes:
    - ``manual`` (default): caller provides ``variant`` → freeze it.
    - ``auto``: ignore ``variant``; compute current performance and
      promote the leader iff ``sent_A >= min_samples`` AND
      ``sent_B >= min_samples`` AND the open-rate gap between leader
      and loser is ``>= min_lift_pct`` percentage points. Otherwise
      return HTTP 409 with the reason so the UI can surface it.
    """
    await require_admin(request)
    bucket = body.bucket.strip().lower()
    mode = (body.mode or "manual").strip().lower()
    if bucket not in _VALID_BUCKETS:
        raise HTTPException(status_code=400, detail=f"bucket must be one of {_VALID_BUCKETS}")
    if mode not in ("manual", "auto"):
        raise HTTPException(status_code=400, detail="mode must be 'manual' or 'auto'")

    decision: dict | None = None
    if mode == "manual":
        variant = (body.variant or "").strip().upper()
        if variant not in ("A", "B"):
            raise HTTPException(status_code=400, detail="variant must be 'A' or 'B' in manual mode")
    else:
        # Auto: consult current performance
        perf = await _compute_ab_performance()
        row = next((b for b in perf["buckets"] if b["bucket"] == bucket), None)
        if row is None:
            raise HTTPException(status_code=409, detail={
                "reason": "no_data",
                "bucket": bucket,
                "message": f"No A/B data yet for bucket '{bucket}' — promote manually or wait for the next digest cycle.",
            })
        sent_a, sent_b = row["A"]["sent"], row["B"]["sent"]
        rate_a, rate_b = row["A"]["open_rate"], row["B"]["open_rate"]
        if sent_a < body.min_samples or sent_b < body.min_samples:
            raise HTTPException(status_code=409, detail={
                "reason": "insufficient_samples",
                "bucket": bucket,
                "sent_a": sent_a,
                "sent_b": sent_b,
                "required": body.min_samples,
                "message": f"Need ≥{body.min_samples} sends per variant. Current: A={sent_a}, B={sent_b}.",
            })
        lift = abs(rate_a - rate_b)
        if lift < body.min_lift_pct:
            raise HTTPException(status_code=409, detail={
                "reason": "insufficient_lift",
                "bucket": bucket,
                "rate_a": rate_a,
                "rate_b": rate_b,
                "lift_pct": round(lift, 2),
                "required": body.min_lift_pct,
                "message": f"Gap {lift:.2f}pp < min_lift {body.min_lift_pct}pp — experiment is still a coin flip.",
            })
        variant = "A" if rate_a > rate_b else "B"
        decision = {
            "mode": "auto",
            "rate_a": rate_a,
            "rate_b": rate_b,
            "lift_pct": round(lift, 2),
            "sent_a": sent_a,
            "sent_b": sent_b,
            "min_samples": body.min_samples,
            "min_lift_pct": body.min_lift_pct,
        }

    subject = _SUBJECT_AB_VARIANTS.get(bucket, {}).get(variant, "")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "bucket": bucket,
        "variant": variant,
        "subject": subject,
        "promoted_at": now,
        "promoted_by": mode,
    }
    if decision is not None:
        doc["decision"] = decision
    await _db_mod.db.newsletter_ab_winners.update_one(
        {"bucket": bucket}, {"$set": doc}, upsert=True
    )
    await _load_frozen_winners_from_db()
    logger.info(
        f"[newsletter-ab] winner promoted bucket={bucket} variant={variant} mode={mode}"
    )
    return {
        "ok": True,
        "bucket": bucket,
        "variant": variant,
        "subject": subject,
        "mode": mode,
        "decision": decision,
        "frozen_winners": dict(_FROZEN_WINNERS),
    }


@router.post("/ab/revert-winner")
async def revert_ab_winner(body: RevertWinnerBody, request: Request):
    """Remove a frozen winner — re-open the A/B split for that bucket."""
    await require_admin(request)
    bucket = body.bucket.strip().lower()
    if bucket not in _VALID_BUCKETS:
        raise HTTPException(status_code=400, detail=f"bucket must be one of {_VALID_BUCKETS}")

    res = await _db_mod.db.newsletter_ab_winners.delete_one({"bucket": bucket})
    await _load_frozen_winners_from_db()
    logger.info(f"[newsletter-ab] winner reverted bucket={bucket} removed={res.deleted_count}")
    return {
        "ok": True,
        "bucket": bucket,
        "removed": res.deleted_count,
        "frozen_winners": dict(_FROZEN_WINNERS),
    }


@router.get("/ab/frozen-winners")
async def list_frozen_ab_winners(request: Request):
    """List the current frozen winners — the admin UI reads this."""
    await require_admin(request)
    await _load_frozen_winners_from_db()
    return {
        "frozen_winners": dict(_FROZEN_WINNERS),
        "variants": _SUBJECT_AB_VARIANTS,
    }

