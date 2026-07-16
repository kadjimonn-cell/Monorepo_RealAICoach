"""Weekly Hiring Analytics Report — Automated email digest for admins.

Functions:
- send_weekly_hiring_report()  Compiles and sends hiring KPI summary email
Endpoints:
- POST /api/hiring-reports/send-now           Manually trigger report (admin only)
- GET  /api/hiring-reports/settings            Get report settings
- POST /api/hiring-reports/settings            Update report settings
"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import logging

from .db import db, require_admin

router = APIRouter(prefix="/hiring-reports")
logger = logging.getLogger("routes.weekly_hiring_report")


async def _compile_hiring_kpis():
    """Compile weekly hiring KPIs from the database."""
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    prev_week = (now - timedelta(days=14)).isoformat()

    # Pipeline metrics
    all_pipes = await db.hiring_pipeline.find(
        {}, {"_id": 0, "created_at": 1, "current_stage": 1, "prediction": 1, "status": 1}
    ).to_list(500)
    new_pipes = [p for p in all_pipes if p.get("created_at", "") >= week_ago]
    prev_pipes = [p for p in all_pipes if prev_week <= p.get("created_at", "") < week_ago]

    active = sum(
        1 for p in all_pipes if p.get("status") == "active" or p.get("current_stage") != "offer_recommendation"
    )
    completed = sum(1 for p in all_pipes if p.get("current_stage") == "offer_recommendation")

    # AI confidence
    confs = [
        p["prediction"]["hire_confidence"] for p in all_pipes if (p.get("prediction") or {}).get("hire_confidence")
    ]
    avg_conf = round(sum(confs) / max(len(confs), 1), 1)

    # Interview metrics
    all_intvs = await db.interview_bookings.count_documents({})
    new_intvs = await db.interview_bookings.count_documents({"created_at": {"$gte": week_ago}})
    completed_intvs = await db.interview_bookings.count_documents({"status": "completed"})
    completion_rate = round(completed_intvs / max(all_intvs, 1) * 100, 1)

    # Applications
    total_apps = await db.job_applications.count_documents({})
    new_apps = await db.job_applications.count_documents({"applied_at": {"$gte": week_ago}})

    # Fairness flags
    open_flags = await db.fairness_flags.count_documents({"status": "open"})

    # Candidate experience
    exp_docs = await db.candidate_experience.find(
        {"created_at": {"$gte": week_ago}}, {"_id": 0, "overall_rating": 1}
    ).to_list(500)
    avg_exp = round(sum(e["overall_rating"] for e in exp_docs) / max(len(exp_docs), 1), 1) if exp_docs else 0

    # AI accuracy
    accuracy_doc = await db.ai_calibrations.find_one({}, {"_id": 0, "accuracy_pct": 1}, sort=[("created_at", -1)])
    ai_accuracy = accuracy_doc.get("accuracy_pct", 0) if accuracy_doc else 0

    return {
        "period": f"{(now - timedelta(days=7)).strftime('%b %d')} - {now.strftime('%b %d, %Y')}",
        "total_pipelines": len(all_pipes),
        "new_pipelines": len(new_pipes),
        "prev_week_pipelines": len(prev_pipes),
        "active_pipelines": active,
        "completed_pipelines": completed,
        "avg_confidence": avg_conf,
        "total_interviews": all_intvs,
        "new_interviews": new_intvs,
        "interview_completion_rate": completion_rate,
        "total_applications": total_apps,
        "new_applications": new_apps,
        "open_fairness_flags": open_flags,
        "avg_candidate_experience": avg_exp,
        "ai_accuracy": ai_accuracy,
    }


def _build_email_html(kpis: dict) -> str:
    """Generate an executive HTML email from KPI data."""
    from utils.email_service import render_email_header_panel

    pipe_trend = (
        "up"
        if kpis["new_pipelines"] > kpis["prev_week_pipelines"]
        else "down"
        if kpis["new_pipelines"] < kpis["prev_week_pipelines"]
        else "flat"
    )
    trend_arrow = {"up": "&#9650;", "down": "&#9660;", "flat": "&#9644;"}.get(pipe_trend, "")
    trend_color = {"up": "#10B981", "down": "#EF4444", "flat": "#6B7280"}.get(pipe_trend, "#6B7280")
    header_html = render_email_header_panel(
        title="Hiring Intelligence Report",
        subtitle=f"Weekly hiring digest for {kpis['period']}.",
        variant="report",
        accent="#6366F1",
        meta_label="Period",
        meta_value=kpis["period"],
    )

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #0F172A; color: #E2E8F0; border-radius: 16px; overflow: hidden;">
      {header_html}
      <div style="padding: 24px;">
        <h2 style="color: #A78BFA; font-size: 16px; margin: 0 0 16px; border-bottom: 1px solid #334155; padding-bottom: 8px;">Pipeline Summary</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">Total Pipelines</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #E2E8F0;">{kpis["total_pipelines"]}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">New This Week</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: {trend_color};">{kpis["new_pipelines"]} <span style="font-size: 12px;">{trend_arrow}</span></td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">Active</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #6366F1;">{kpis["active_pipelines"]}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">Completed</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #10B981;">{kpis["completed_pipelines"]}</td>
          </tr>
        </table>

        <h2 style="color: #A78BFA; font-size: 16px; margin: 24px 0 16px; border-bottom: 1px solid #334155; padding-bottom: 8px;">Key Metrics</h2>
        <div style="display: flex; flex-wrap: wrap; gap: 12px;">
          <div style="flex: 1; min-width: 120px; background: #1E293B; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: #6366F1;">{kpis["avg_confidence"]}%</div>
            <div style="font-size: 12px; color: #94A3B8; margin-top: 4px;">AI Confidence</div>
          </div>
          <div style="flex: 1; min-width: 120px; background: #1E293B; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: #10B981;">{kpis["interview_completion_rate"]}%</div>
            <div style="font-size: 12px; color: #94A3B8; margin-top: 4px;">Interview Completion</div>
          </div>
          <div style="flex: 1; min-width: 120px; background: #1E293B; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: #F59E0B;">{kpis["new_applications"]}</div>
            <div style="font-size: 12px; color: #94A3B8; margin-top: 4px;">New Applications</div>
          </div>
        </div>

        <h2 style="color: #A78BFA; font-size: 16px; margin: 24px 0 16px; border-bottom: 1px solid #334155; padding-bottom: 8px;">Interviews</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">Total Interviews</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #E2E8F0;">{kpis["total_interviews"]}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">New This Week</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #6366F1;">{kpis["new_interviews"]}</td>
          </tr>
        </table>

        <h2 style="color: #A78BFA; font-size: 16px; margin: 24px 0 16px; border-bottom: 1px solid #334155; padding-bottom: 8px;">AI & Fairness</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">AI Accuracy</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: {"#10B981" if kpis["ai_accuracy"] >= 80 else "#F59E0B"};">{kpis["ai_accuracy"]}%</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">Open Fairness Flags</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: {"#EF4444" if kpis["open_fairness_flags"] > 0 else "#10B981"};">{kpis["open_fairness_flags"]}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94A3B8;">Avg Candidate Experience</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #F59E0B;">{kpis["avg_candidate_experience"]}/5</td>
          </tr>
        </table>
      </div>
      <div style="background: #1E293B; padding: 16px 24px; text-align: center; border-top: 1px solid #334155;">
        <p style="margin: 0; color: #64748B; font-size: 12px;">ARIS Hiring Intelligence | Generated {datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")}</p>
      </div>
    </div>"""


async def send_weekly_hiring_report():
    """Compile and email the weekly hiring analytics digest to all admins."""
    # Check settings
    settings = await db.hiring_report_settings.find_one({}, {"_id": 0}) or {}
    if not settings.get("enabled", True):
        logger.info("Weekly hiring report disabled by admin")
        return

    from utils.email_service import is_email_configured, send_catalog_template

    if not is_email_configured():
        logger.warning("Email service not configured - skipping weekly hiring report")
        return

    kpis = await _compile_hiring_kpis()
    _build_email_html(kpis)

    # Get all admin emails
    admins = await db.users.find({"is_admin": True}, {"_id": 0, "email": 1, "name": 1}).to_list(50)

    sent = 0
    for admin in admins:
        result = await send_catalog_template(
            recipient_email=admin["email"],
            template_key="weekly_hiring_report",
            recipient_name=admin.get("name", "Admin"),
            week_label=kpis['period'],
            new_applicants=kpis.get("new_applicants", 0),
            interviews_scheduled=kpis.get("interviews_scheduled", 0),
            offers_sent=kpis.get("offers_sent", 0),
            pipeline_total=kpis.get("pipeline_total", 0),
        )
        if result.get("success"):
            sent += 1

    # Log the report
    await db.hiring_weekly_reports.insert_one(
        {
            "period": kpis["period"],
            "kpis": kpis,
            "sent_to": len(admins),
            "delivered": sent,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    logger.info(f"Weekly hiring report sent to {sent}/{len(admins)} admins")
    return {"sent": sent, "total_admins": len(admins), "kpis": kpis}


# ── API Endpoints ──


@router.post("/send-now")
async def trigger_report_now(request: Request):
    """Manually trigger the weekly hiring report (admin only)."""
    await require_admin(request)
    result = await send_weekly_hiring_report()
    return result or {"sent": 0, "message": "Report disabled or email not configured"}


@router.get("/settings")
async def get_report_settings(request: Request):
    """Get weekly hiring report settings."""
    await require_admin(request)
    settings = await db.hiring_report_settings.find_one({}, {"_id": 0}) or {
        "enabled": True,
        "day_of_week": "monday",
        "hour_utc": 9,
    }
    # Get last report
    last = await db.hiring_weekly_reports.find_one(
        {}, {"_id": 0, "period": 1, "sent_to": 1, "delivered": 1, "generated_at": 1}, sort=[("generated_at", -1)]
    )
    settings["last_report"] = last
    return settings


@router.post("/settings")
async def update_report_settings(request: Request):
    """Update weekly hiring report settings."""
    await require_admin(request)
    body = await request.json()
    allowed = {"enabled", "day_of_week", "hour_utc"}
    update = {k: v for k, v in body.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.hiring_report_settings.update_one({}, {"$set": update}, upsert=True)
    return {"success": True, **update}
