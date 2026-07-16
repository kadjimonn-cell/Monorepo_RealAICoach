"""Churn Recovery Admin API — Dashboard analytics and management for win-back campaigns."""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException
from routes.db import db, require_auth

router = APIRouter(prefix="/churn-recovery", tags=["churn-recovery"])

log = __import__("logging").getLogger(__name__)


async def _require_admin(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin access required")
    return user


@router.get("/admin/dashboard")
async def churn_dashboard(request: Request):
    """Full churn recovery analytics dashboard for admin."""
    await _require_admin(request)
    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    (now - timedelta(days=90)).isoformat()

    # Total churn records
    all_records = await db.churn_recovery.find({}, {"_id": 0}).sort("cancelled_at", -1).to_list(500)

    total_churned = len(all_records)
    recovered = [r for r in all_records if r.get("status") == "recovered"]
    active_campaigns = [r for r in all_records if r.get("status") in ("churned", "winback_sent")]
    expired_campaigns = [r for r in all_records if r.get("status") == "expired"]
    redeemed_codes = [r for r in all_records if r.get("discount_redeemed")]

    # Recovery rate
    recovery_rate = (len(recovered) / total_churned * 100) if total_churned > 0 else 0

    # Revenue impact estimate (assume avg $29/month subscription)
    AVG_MONTHLY = 29
    estimated_recovered_revenue = len(recovered) * AVG_MONTHLY * 3  # 3-month avg LTV

    # 30-day churn trend
    recent_churns = [r for r in all_records if r.get("cancelled_at", "") >= thirty_days_ago]
    recent_recovered = [r for r in recovered if r.get("recovered_at", "") >= thirty_days_ago]

    # Churn by day (last 30 days)
    churn_trend = {}
    recovery_trend = {}
    for i in range(30):
        day = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        churn_trend[day] = 0
        recovery_trend[day] = 0
    for r in all_records:
        day = r.get("cancelled_at", "")[:10]
        if day in churn_trend:
            churn_trend[day] += 1
    for r in recovered:
        day = (r.get("recovered_at") or "")[:10]
        if day in recovery_trend:
            recovery_trend[day] += 1

    # Reminder effectiveness
    total_emails_sent = sum(len(r.get("email_history", [])) for r in all_records)
    reminder_stage_recovery = {}
    for r in recovered:
        stage = r.get("reminders_sent", 0)
        reminder_stage_recovery[stage] = reminder_stage_recovery.get(stage, 0) + 1

    # Recovery funnel
    funnel = {
        "total_cancelled": total_churned,
        "emails_sent": total_emails_sent,
        "active_campaigns": len(active_campaigns),
        "recovered": len(recovered),
        "expired": len(expired_campaigns),
    }

    # Top churned users (recent, for management table)
    users_list = []
    for r in all_records[:50]:
        total_reminders = r.get("reminders_sent", 0)
        emails = r.get("email_history", [])
        users_list.append(
            {
                "churn_id": r.get("churn_id"),
                "user_id": r.get("user_id"),
                "user_email": r.get("user_email"),
                "user_name": r.get("user_name"),
                "cancelled_at": r.get("cancelled_at"),
                "status": r.get("status"),
                "discount_code": r.get("discount_code"),
                "discount_redeemed": r.get("discount_redeemed", False),
                "reminders_sent": total_reminders,
                "last_reminder_at": r.get("last_reminder_at"),
                "recovered_at": r.get("recovered_at"),
                "next_reminder_at": r.get("next_reminder_at"),
                "emails_sent": len(emails),
            }
        )

    return {
        "kpis": {
            "total_churned": total_churned,
            "recovered": len(recovered),
            "recovery_rate": round(recovery_rate, 1),
            "active_campaigns": len(active_campaigns),
            "estimated_recovered_revenue": estimated_recovered_revenue,
            "codes_redeemed": len(redeemed_codes),
            "total_emails_sent": total_emails_sent,
            "recent_churns_30d": len(recent_churns),
            "recent_recovered_30d": len(recent_recovered),
        },
        "churn_trend": [{"date": k, "churns": v} for k, v in churn_trend.items()],
        "recovery_trend": [{"date": k, "recoveries": v} for k, v in recovery_trend.items()],
        "funnel": funnel,
        "reminder_effectiveness": reminder_stage_recovery,
        "users": users_list,
    }


@router.post("/admin/send-winback/{churn_id}")
async def manual_send_winback(request: Request, churn_id: str):
    """Manually trigger a win-back email for a specific user."""
    await _require_admin(request)
    record = await db.churn_recovery.find_one({"churn_id": churn_id}, {"_id": 0})
    if not record:
        raise HTTPException(404, "Churn record not found")

    from services.churn_recovery import (
        _build_winback_reminder_html,
        DISCOUNT_PERCENT,
        REMINDER_INTERVAL_DAYS,
    )

    now = datetime.now(timezone.utc)
    reminder_num = record.get("reminders_sent", 0) + 1
    discount_expiry = datetime.fromisoformat(record["discount_expiry"].replace("Z", "+00:00")).strftime("%B %d, %Y")

    _build_winback_reminder_html(record["user_name"], record["discount_code"], discount_expiry, reminder_num)
    from utils.email_service import send_catalog_template
    result = await send_catalog_template(
        recipient_email=record["user_email"],
        template_key="churn_winback",
        recipient_name=record["user_name"],
        user_name=record["user_name"],
        days_inactive=record.get("days_inactive", 30),
        special_offer=f"{DISCOUNT_PERCENT}% off your next month",
    )

    await db.churn_recovery.update_one(
        {"churn_id": churn_id},
        {
            "$set": {
                "reminders_sent": reminder_num,
                "last_reminder_at": now.isoformat(),
                "status": "winback_sent",
                "next_reminder_at": (now + timedelta(days=REMINDER_INTERVAL_DAYS)).isoformat(),
            },
            "$push": {
                "email_history": {
                    "type": f"manual_reminder_{reminder_num}",
                    "sent_at": now.isoformat(),
                    "success": result.get("success", False),
                    "message_id": result.get("message_id", ""),
                }
            },
        },
    )
    return {"success": True, "reminder_number": reminder_num}


@router.post("/admin/mark-recovered/{churn_id}")
async def mark_recovered(request: Request, churn_id: str):
    """Manually mark a churned user as recovered."""
    await _require_admin(request)
    now = datetime.now(timezone.utc).isoformat()
    result = await db.churn_recovery.update_one(
        {"churn_id": churn_id}, {"$set": {"status": "recovered", "recovered_at": now}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Record not found")
    return {"success": True}


@router.get("/admin/email-preview/{template_type}")
async def preview_email(request: Request, template_type: str):
    """Preview cancellation or win-back email templates."""
    await _require_admin(request)
    from services.churn_recovery import _build_cancellation_email_html, _build_winback_reminder_html

    if template_type == "cancellation":
        html = _build_cancellation_email_html("John Doe", "COMEBACKABC123", "April 10, 2026")
    elif template_type.startswith("reminder"):
        num = int(template_type.replace("reminder", "") or "1")
        html = _build_winback_reminder_html("John Doe", "COMEBACKABC123", "April 10, 2026", num)
    else:
        raise HTTPException(400, "Invalid template type. Use 'cancellation' or 'reminder1'-'reminder6'")
    return {"html": html, "template_type": template_type}
