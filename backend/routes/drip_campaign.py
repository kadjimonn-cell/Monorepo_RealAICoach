"""Automated 5-day onboarding drip campaign engine.

Sends personalized emails to new users over 5 days:
  Day 1: Welcome + Quick Start Guide
  Day 2: AI Coaching Tips & Best Practices
  Day 3: Feature Highlights (30+ AI tools)
  Day 4: Power User Tips (automations, exports)
  Day 5: Limited-time Upgrade Offer (30% off)

Fully automated via APScheduler — zero admin input required.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from routes.db import db, get_current_user
from utils.email_service import send_catalog_template, is_email_configured
from utils.email_templates import (
    build_drip_day1,
    build_drip_day2,
    build_drip_day3,
    build_drip_day4,
    build_drip_day5,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding-drip", tags=["Onboarding Drip"])

DRIP_BUILDERS = {
    1: build_drip_day1,
    2: build_drip_day2,
    3: build_drip_day3,
    4: build_drip_day4,
    5: build_drip_day5,
}


async def process_drip_campaigns():
    """Run by scheduler: find users due for drip emails and send them."""
    if not is_email_configured():
        logger.warning("Drip campaign skipped: email not configured")
        return 0

    now = datetime.now(timezone.utc)
    sent_count = 0

    for day_num in range(1, 6):
        # Find users who signed up exactly (day_num) days ago
        target_start = (now - timedelta(days=day_num)).replace(hour=0, minute=0, second=0, microsecond=0)
        target_end = target_start + timedelta(days=1)

        users = await db.users.find(
            {
                "created_at": {
                    "$gte": target_start.isoformat(),
                    "$lt": target_end.isoformat(),
                },
                "subscription_plan": "free",  # Only drip to free users
                "email_verified": {"$ne": False},
            },
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(500)

        for user in users:
            uid = user["user_id"]
            email = user.get("email", "")
            name = user.get("name", "") or email.split("@")[0]

            if not email:
                continue

            # Check if already sent this day's drip
            existing = await db.drip_campaign.find_one(
                {"user_id": uid, "day": day_num}
            )
            if existing:
                continue

            # Check opt-out
            opted_out = await db.drip_campaign.find_one(
                {"user_id": uid, "opted_out": True}
            )
            if opted_out:
                continue

            # Build and send
            builder = DRIP_BUILDERS.get(day_num)
            if not builder:
                continue

            try:
                kwargs = {"user_name": name}
                if day_num == 5:
                    kwargs["discount_pct"] = 30

                template = builder(**kwargs)

                await send_catalog_template(
                    recipient_email=email,
                    template_key=f"drip_day{day_num}",
                    recipient_name=name,
                    **kwargs,
                )

                # Record sent
                await db.drip_campaign.insert_one({
                    "drip_id": f"drip_{uuid.uuid4().hex[:12]}",
                    "user_id": uid,
                    "day": day_num,
                    "template_key": f"drip_day{day_num}",
                    "sent_at": now.isoformat(),
                    "email": email,
                })

                # Also create in-app notification
                await db.notifications.insert_one({
                    "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": uid,
                    "type": f"drip_day{day_num}",
                    "title": template.subject,
                    "body": "Check your email for today's coaching tip!",
                    "action_url": "/",
                    "read": False,
                    "created_at": now.isoformat(),
                })

                sent_count += 1
                logger.info(f"Drip day {day_num} sent to {uid}")

            except Exception as e:
                logger.error(f"Drip day {day_num} failed for {uid}: {e}")

    if sent_count:
        logger.info(f"Drip campaign: {sent_count} emails sent")
    return sent_count


@router.get("/status")
async def get_drip_status(request: Request):
    """Get the current user's drip campaign progress."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    records = await db.drip_campaign.find(
        {"user_id": user.user_id, "day": {"$exists": True}},
        {"_id": 0},
    ).sort("day", 1).to_list(10)

    opted_out = await db.drip_campaign.find_one(
        {"user_id": user.user_id, "opted_out": True}
    )

    days_sent = [r["day"] for r in records]
    total_days = 5
    progress_pct = int((len(days_sent) / total_days) * 100)

    return {
        "user_id": user.user_id,
        "days_completed": days_sent,
        "total_days": total_days,
        "progress_percent": progress_pct,
        "opted_out": bool(opted_out),
        "campaign_complete": len(days_sent) >= total_days,
        "records": records,
    }


@router.post("/opt-out")
async def opt_out_drip(request: Request):
    """Opt out of the onboarding drip campaign."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.drip_campaign.update_one(
        {"user_id": user.user_id, "opted_out": True},
        {"$set": {
            "user_id": user.user_id,
            "opted_out": True,
            "opted_out_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"success": True, "message": "You've been opted out of the onboarding email series."}


@router.post("/opt-in")
async def opt_in_drip(request: Request):
    """Re-opt into the onboarding drip campaign."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.drip_campaign.delete_one({"user_id": user.user_id, "opted_out": True})
    return {"success": True, "message": "You've been opted back into the onboarding email series."}


@router.get("/preview/{day}")
async def preview_drip_email(day: int):
    """Preview a drip email template (admin use)."""
    if day < 1 or day > 5:
        raise HTTPException(status_code=400, detail="Day must be 1-5")

    builder = DRIP_BUILDERS.get(day)
    if not builder:
        raise HTTPException(status_code=404, detail="Template not found")

    if day == 5:
        template = builder(user_name="Demo User", discount_pct=30)
    else:
        template = builder(user_name="Demo User")

    return {
        "day": day,
        "subject": template.subject,
        "html": template.html,
        "text": template.text,
    }
