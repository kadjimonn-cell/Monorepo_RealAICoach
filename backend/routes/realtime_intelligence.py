"""Real-Time Intelligence — Live hiring updates, dashboard counters, event stream.

Endpoints:
- GET /api/realtime/hiring-stats       Live hiring dashboard stats (employer/admin)
- GET /api/realtime/candidate-alerts   Live candidate alerts (application updates, job matches)
- GET /api/realtime/activity-feed      Recent activity feed across hiring system
"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import logging

from .db import db, require_auth, require_admin

router = APIRouter(prefix="/realtime")
logger = logging.getLogger("routes.realtime")


@router.get("/hiring-stats")
async def live_hiring_stats(request: Request):
    """Live hiring dashboard counters for employers and admins."""
    user = await require_auth(request)
    uid = user.user_id
    is_admin = user.is_admin
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    # Active pipelines
    pipe_query = {} if is_admin else {"employer_id": uid}
    active_pipes = await db.hiring_pipeline.count_documents(
        {**pipe_query, "current_stage": {"$ne": "offer_recommendation"}}
    )
    completed_pipes = await db.hiring_pipeline.count_documents({**pipe_query, "current_stage": "offer_recommendation"})
    total_pipes = await db.hiring_pipeline.count_documents(pipe_query)

    # Interviews
    iv_query = {} if is_admin else {"employer_id": uid}
    pending_interviews = await db.interview_bookings.count_documents(
        {**iv_query, "status": {"$in": ["scheduled", "confirmed"]}}
    )
    today_interviews = await db.interview_bookings.count_documents(
        {
            **iv_query,
            "status": {"$in": ["scheduled", "confirmed"]},
            "scheduled_date": {"$gte": today},
        }
    )
    completed_interviews = await db.interview_bookings.count_documents({**iv_query, "status": "completed"})

    # New applications (last 7 days)
    new_apps_query = {"created_at": {"$gte": week_ago}}
    if not is_admin:
        new_apps_query["employer_id"] = uid
    new_applications = await db.job_applications.count_documents(new_apps_query)

    # Active jobs
    job_query = {} if is_admin else {"poster_user_id": uid}
    active_jobs = await db.jobs.count_documents({**job_query, "status": {"$in": ["open", "active"]}})

    # Recent stage advances (last 24h)
    yesterday = (now - timedelta(hours=24)).isoformat()
    recent_pipes = await db.hiring_pipeline.find(
        {**pipe_query, "updated_at": {"$gte": yesterday}},
        {"_id": 0, "pipeline_id": 1, "candidate_id": 1, "current_stage": 1, "updated_at": 1},
    ).to_list(20)

    # Active video rooms
    active_rooms = await db.interview_rooms.count_documents({"status": {"$in": ["waiting", "active"]}})

    return {
        "pipelines": {
            "active": active_pipes,
            "completed": completed_pipes,
            "total": total_pipes,
        },
        "interviews": {
            "pending": pending_interviews,
            "today": today_interviews,
            "completed": completed_interviews,
        },
        "applications": {
            "new_this_week": new_applications,
        },
        "jobs": {
            "active": active_jobs,
        },
        "live": {
            "active_video_rooms": active_rooms,
            "recent_advances": len(recent_pipes),
        },
        "recent_pipeline_updates": recent_pipes,
        "timestamp": now.isoformat(),
    }


@router.get("/candidate-alerts")
async def candidate_alerts(request: Request):
    """Live alerts for candidates: application status changes, job matches, interview updates."""
    user = await require_auth(request)
    uid = user.user_id
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    alerts = []

    # 1. Pipeline status updates
    my_pipes = (
        await db.hiring_pipeline.find({"candidate_id": uid, "updated_at": {"$gte": week_ago}}, {"_id": 0})
        .sort("updated_at", -1)
        .to_list(10)
    )

    for p in my_pipes:
        alerts.append(
            {
                "type": "pipeline_update",
                "title": f"Application Update: {p.get('job_title', 'Position')}",
                "message": f"Your application is now at: {p.get('current_stage', 'unknown').replace('_', ' ').title()}",
                "pipeline_id": p.get("pipeline_id"),
                "timestamp": p.get("updated_at"),
                "priority": "high"
                if p.get("current_stage") in ("offer_recommendation", "interview_scheduling")
                else "normal",
            }
        )

    # 2. Interview updates
    my_interviews = (
        await db.interview_bookings.find({"candidate_id": uid, "updated_at": {"$gte": week_ago}}, {"_id": 0})
        .sort("updated_at", -1)
        .to_list(10)
    )

    for iv in my_interviews:
        status = iv.get("status", "")
        if status == "scheduled":
            msg = f"Interview scheduled for {iv.get('job_title', 'position')} on {iv.get('scheduled_date', 'TBD')}"
        elif status == "completed":
            msg = f"Interview completed for {iv.get('job_title', 'position')}"
        elif status == "cancelled":
            msg = f"Interview cancelled for {iv.get('job_title', 'position')}"
        else:
            msg = f"Interview status: {status} for {iv.get('job_title', 'position')}"
        alerts.append(
            {
                "type": "interview_update",
                "title": f"Interview: {iv.get('job_title', '')}",
                "message": msg,
                "interview_id": iv.get("interview_id"),
                "timestamp": iv.get("updated_at"),
                "priority": "high" if status in ("scheduled", "confirmed") else "normal",
            }
        )

    # 3. New job matches (from daily suggestions)
    suggestions = (
        await db.daily_suggestions.find({"candidate_id": uid, "created_at": {"$gte": week_ago}}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(5)
    )

    for s in suggestions:
        for job in s.get("suggestions", [])[:3]:
            alerts.append(
                {
                    "type": "job_match",
                    "title": f"New Match: {job.get('title', 'Job')}",
                    "message": f"AI found a {job.get('match_score', 0)}% match at {job.get('company', 'company')}",
                    "job_id": job.get("job_id"),
                    "timestamp": s.get("created_at"),
                    "priority": "normal",
                }
            )

    # Sort by timestamp
    alerts.sort(key=lambda a: a.get("timestamp", ""), reverse=True)

    return {
        "alerts": alerts[:20],
        "total": len(alerts),
        "unread": len(alerts),  # All recent ones count as unread
        "timestamp": now.isoformat(),
    }


@router.get("/activity-feed")
async def activity_feed(request: Request):
    """Recent activity feed across the hiring system (admin view)."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    feed = []

    # Recent pipeline updates
    pipes = (
        await db.hiring_pipeline.find(
            {"updated_at": {"$gte": day_ago}},
            {"_id": 0, "pipeline_id": 1, "candidate_id": 1, "job_title": 1, "current_stage": 1, "updated_at": 1},
        )
        .sort("updated_at", -1)
        .to_list(20)
    )
    for p in pipes:
        feed.append(
            {
                "type": "pipeline",
                "action": f"Pipeline advanced to {p.get('current_stage', '').replace('_', ' ').title()}",
                "subject": p.get("job_title", "Position"),
                "actor_id": p.get("candidate_id"),
                "timestamp": p.get("updated_at"),
            }
        )

    # Recent interviews
    ivs = (
        await db.interview_bookings.find(
            {"updated_at": {"$gte": day_ago}},
            {"_id": 0, "interview_id": 1, "job_title": 1, "status": 1, "candidate_name": 1, "updated_at": 1},
        )
        .sort("updated_at", -1)
        .to_list(20)
    )
    for iv in ivs:
        feed.append(
            {
                "type": "interview",
                "action": f"Interview {iv.get('status', 'updated')}",
                "subject": f"{iv.get('candidate_name', 'Candidate')} - {iv.get('job_title', 'Position')}",
                "timestamp": iv.get("updated_at"),
            }
        )

    # Recent video rooms
    rooms = (
        await db.interview_rooms.find(
            {"created_at": {"$gte": day_ago}}, {"_id": 0, "room_id": 1, "job_title": 1, "status": 1, "created_at": 1}
        )
        .sort("created_at", -1)
        .to_list(10)
    )
    for r in rooms:
        feed.append(
            {
                "type": "video_room",
                "action": f"Video room {r.get('status', 'created')}",
                "subject": r.get("job_title", "Interview Room"),
                "timestamp": r.get("created_at"),
            }
        )

    feed.sort(key=lambda f: f.get("timestamp", ""), reverse=True)

    return {
        "feed": feed[:30],
        "total": len(feed),
        "period": "24h",
        "timestamp": now.isoformat(),
    }
