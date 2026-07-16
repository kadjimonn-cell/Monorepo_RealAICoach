"""Hiring Analytics Export — Executive-grade analytics and report generation.

Endpoints:
- GET /api/hiring-analytics/executive     Full executive hiring report
- GET /api/hiring-analytics/export/csv    Export hiring data as CSV
- GET /api/hiring-analytics/trends        Hiring trends over time
- GET /api/hiring-analytics/roi           Hiring ROI and efficiency metrics
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from datetime import datetime, timezone, timedelta
import io
import csv
import logging

from .db import db, require_admin

router = APIRouter(prefix="/hiring-analytics")
logger = logging.getLogger("routes.hiring_analytics")


@router.get("/executive")
async def executive_report(request: Request):
    """Full executive hiring analytics report."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    month_ago = (now - timedelta(days=30)).isoformat()
    (now - timedelta(days=7)).isoformat()

    # Pipeline metrics
    all_pipes = await db.hiring_pipeline.find({}, {"_id": 0}).to_list(500)
    recent_pipes = [p for p in all_pipes if (p.get("created_at", "") >= month_ago)]

    stage_counts = {}
    for p in all_pipes:
        stage = p.get("current_stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    # Decision metrics
    decisions = {}
    confidence_sum = 0
    confidence_count = 0
    for p in all_pipes:
        pred = p.get("prediction") or {}
        dec = pred.get("recommendation", "pending")
        decisions[dec] = decisions.get(dec, 0) + 1
        conf = pred.get("hire_confidence")
        if conf is not None:
            confidence_sum += conf
            confidence_count += 1

    # Interview metrics
    all_interviews = await db.interview_bookings.find({}, {"_id": 0}).to_list(500)
    recent_interviews = [iv for iv in all_interviews if (iv.get("created_at", "") >= month_ago)]

    iv_status = {}
    for iv in all_interviews:
        s = iv.get("status", "unknown")
        iv_status[s] = iv_status.get(s, 0) + 1

    # Video room stats
    all_rooms = await db.interview_rooms.find({}, {"_id": 0}).to_list(200)
    total_room_duration = sum(r.get("duration_seconds", 0) or 0 for r in all_rooms if r.get("status") == "ended")

    # AI accuracy (outcomes)
    outcomes = await db.ai_outcomes.find({}, {"_id": 0}).to_list(200)
    correct = sum(1 for o in outcomes if o.get("ai_correct") is True)
    incorrect = sum(1 for o in outcomes if o.get("ai_correct") is False)
    evaluated = correct + incorrect

    # Fairness
    flags = await db.fairness_flags.find({}, {"_id": 0}).to_list(200)
    pending_flags = sum(1 for f in flags if f.get("status") == "pending")

    # Candidate experience
    cx_ratings = await db.candidate_experience.find({}, {"_id": 0}).to_list(200)
    avg_cx = (
        round(sum(r.get("overall_rating", 0) for r in cx_ratings) / max(len(cx_ratings), 1), 1) if cx_ratings else None
    )
    recommend_pct = (
        round(sum(1 for r in cx_ratings if r.get("would_recommend")) / max(len(cx_ratings), 1) * 100, 1)
        if cx_ratings
        else None
    )

    # Jobs
    all_jobs = await db.jobs.find({}, {"_id": 0}).to_list(200)
    active_jobs = sum(1 for j in all_jobs if j.get("status") in ("open", "active"))

    # Applications
    all_apps = await db.job_applications.find({}, {"_id": 0}).to_list(500)
    recent_apps = [a for a in all_apps if a.get("created_at", "") >= month_ago]

    # Summaries generated
    summaries = await db.interview_summaries.count_documents({})

    # Time-to-fill estimate (avg pipeline duration for completed ones)
    completed_pipes = [p for p in all_pipes if p.get("outcome") or p.get("current_stage") == "offer_recommendation"]
    ttf_days = []
    for p in completed_pipes:
        created = p.get("created_at", "")
        updated = p.get("updated_at", "")
        if created and updated:
            try:
                c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                u = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                ttf_days.append((u - c).total_seconds() / 86400)
            except Exception:
                pass
    avg_ttf = round(sum(ttf_days) / len(ttf_days), 1) if ttf_days else None

    # Conversion rates
    total_apps_count = len(all_apps)
    screened = sum(1 for p in all_pipes if p.get("current_stage") not in ("initial_screening", None))
    interviewed = iv_status.get("completed", 0)
    hired = decisions.get("strong_hire", 0) + decisions.get("hire", 0)

    return {
        "report_period": "All Time",
        "generated_at": now.isoformat(),
        "kpi": {
            "total_pipelines": len(all_pipes),
            "new_pipelines_30d": len(recent_pipes),
            "total_interviews": len(all_interviews),
            "new_interviews_30d": len(recent_interviews),
            "active_jobs": active_jobs,
            "total_applications": total_apps_count,
            "new_applications_30d": len(recent_apps),
            "ai_summaries_generated": summaries,
        },
        "hiring_funnel": {
            "applications": total_apps_count,
            "screened": screened,
            "interviewed": interviewed,
            "offered": hired,
            "conversion_rate": round(hired / max(total_apps_count, 1) * 100, 1),
        },
        "efficiency": {
            "avg_time_to_fill_days": avg_ttf,
            "avg_confidence": round(confidence_sum / max(confidence_count, 1), 1),
            "interview_completion_rate": round(iv_status.get("completed", 0) / max(len(all_interviews), 1) * 100, 1),
            "total_video_hours": round(total_room_duration / 3600, 1),
        },
        "ai_performance": {
            "total_outcomes": len(outcomes),
            "accuracy": round(correct / max(evaluated, 1) * 100, 1) if evaluated else None,
            "correct": correct,
            "incorrect": incorrect,
        },
        "pipeline_stages": stage_counts,
        "decision_distribution": decisions,
        "interview_status": iv_status,
        "fairness": {
            "total_flags": len(flags),
            "pending_flags": pending_flags,
            "reviewed": sum(1 for f in flags if f.get("status") == "reviewed"),
        },
        "candidate_experience": {
            "avg_rating": avg_cx,
            "total_ratings": len(cx_ratings),
            "recommend_pct": recommend_pct,
        },
    }


@router.get("/trends")
async def hiring_trends(request: Request):
    """Hiring trends over the last 30 days — daily breakdown."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    daily_data = []
    for i in range(30, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

        pipes = await db.hiring_pipeline.count_documents({"created_at": {"$gte": day_start, "$lte": day_end}})
        interviews = await db.interview_bookings.count_documents({"created_at": {"$gte": day_start, "$lte": day_end}})
        apps = await db.job_applications.count_documents({"created_at": {"$gte": day_start, "$lte": day_end}})

        daily_data.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "day_label": day.strftime("%b %d"),
                "pipelines": pipes,
                "interviews": interviews,
                "applications": apps,
            }
        )

    return {"trends": daily_data, "period": "30d", "generated_at": now.isoformat()}


@router.get("/roi")
async def hiring_roi(request: Request):
    """Hiring ROI and efficiency metrics."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    outcomes = await db.ai_outcomes.find({}, {"_id": 0}).to_list(200)
    interviews = await db.interview_bookings.find({}, {"_id": 0}).to_list(500)
    rooms = await db.interview_rooms.find({}, {"_id": 0}).to_list(200)

    # Interview efficiency
    completed_interviews = [iv for iv in interviews if iv.get("status") == "completed"]
    cancelled_interviews = [iv for iv in interviews if iv.get("status") == "cancelled"]
    no_show = [iv for iv in interviews if iv.get("status") == "no_show"]

    # Video usage
    total_video_minutes = sum((r.get("duration_seconds", 0) or 0) / 60 for r in rooms if r.get("status") == "ended")

    # AI savings (estimated time saved per AI-driven decision)
    ai_decisions = await db.hiring_pipeline.count_documents({"prediction": {"$ne": None}})
    smart_scheduled = await db.interview_bookings.count_documents({"notes": {"$regex": "Smart Scheduler"}})

    # Hire quality (performance ratings)
    perf_ratings = [o.get("performance_rating") for o in outcomes if o.get("performance_rating") is not None]
    avg_perf = round(sum(perf_ratings) / len(perf_ratings), 1) if perf_ratings else None

    # Retention
    retention = [o.get("retention_months") for o in outcomes if o.get("retention_months") is not None]
    avg_retention = round(sum(retention) / len(retention), 1) if retention else None

    return {
        "interview_efficiency": {
            "total": len(interviews),
            "completed": len(completed_interviews),
            "cancelled": len(cancelled_interviews),
            "no_show": len(no_show),
            "completion_rate": round(len(completed_interviews) / max(len(interviews), 1) * 100, 1),
        },
        "video_usage": {
            "total_rooms": len(rooms),
            "total_minutes": round(total_video_minutes, 1),
            "avg_session_minutes": round(
                total_video_minutes / max(len([r for r in rooms if r.get("status") == "ended"]), 1), 1
            ),
        },
        "ai_impact": {
            "ai_decisions_made": ai_decisions,
            "smart_scheduled": smart_scheduled,
            "estimated_hours_saved": round(ai_decisions * 0.5 + smart_scheduled * 0.25, 1),
        },
        "hire_quality": {
            "avg_performance": avg_perf,
            "avg_retention_months": avg_retention,
            "total_outcomes_tracked": len(outcomes),
        },
        "generated_at": now.isoformat(),
    }


@router.get("/export/csv")
async def export_csv(request: Request):
    """Export hiring pipeline data as CSV."""
    await require_admin(request)

    pipelines = await db.hiring_pipeline.find({}, {"_id": 0}).to_list(500)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Pipeline ID",
            "Candidate ID",
            "Employer ID",
            "Job Title",
            "Current Stage",
            "AI Decision",
            "Confidence",
            "Outcome",
            "Created At",
            "Updated At",
        ]
    )

    for p in pipelines:
        pred = p.get("prediction") or {}
        writer.writerow(
            [
                p.get("pipeline_id", ""),
                p.get("candidate_id", ""),
                p.get("employer_id", ""),
                p.get("job_title", ""),
                p.get("current_stage", ""),
                pred.get("recommendation", "pending"),
                pred.get("hire_confidence", ""),
                p.get("outcome", ""),
                p.get("created_at", ""),
                p.get("updated_at", ""),
            ]
        )

    csv_content = output.getvalue()

    # Notify user via email that export is ready
    from utils.email_service import notify_export_ready
    user = getattr(request.state, "user", None)
    if user and getattr(user, "email", None):
        import asyncio
        asyncio.ensure_future(notify_export_ready(user.email, getattr(user, "name", ""), "Hiring Pipeline Data", "CSV"))

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=hiring_analytics_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
        },
    )
