"""Smart Interview Scheduler + Platform Automation Engine.

Features:
- Auto-detect employer & candidate availability
- Suggest optimal interview slots (timezone-aware)
- Interview reminders (24h, 1h, 15m)
- Daily job suggestions for candidates
- Employer notifications for new matches
- Hiring delay detection
- Admin AI Oversight Dashboard
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import uuid
import os
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, require_admin
from utils.ws_manager import ws_manager, push_admin_alert

router = APIRouter(prefix="/smart-scheduler")
logger = logging.getLogger("routes.smart_scheduler")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


async def _ai(system: str, prompt: str) -> str:
    if not EMERGENT_KEY:
        return "{}"
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY, session_id=f"sched_{uuid.uuid4().hex[:8]}", system_message=system
        ).with_model("openai", "gpt-4o")
        return await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.warning(f"AI call failed: {e}")
        return "{}"


def _parse_json(text: str):
    clean = text.strip()
    if "```" in clean:
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else parts[0]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    return json.loads(clean)


# ═══════════════════════════════════════════════════════════════
# SMART INTERVIEW SCHEDULER — AUTO AVAILABILITY DETECTION
# ═══════════════════════════════════════════════════════════════


async def _get_user_busy_slots(user_id: str, start_date: str, end_date: str) -> list:
    """Get busy time ranges from calendar events, bookings, and interviews."""
    busy = []

    # Calendar events
    events = await db.calendar_events.find(
        {"user_id": user_id, "start": {"$gte": start_date, "$lte": end_date}}, {"_id": 0, "start": 1, "end": 1}
    ).to_list(200)
    for e in events:
        try:
            s = datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
            en = datetime.fromisoformat(e["end"].replace("Z", "+00:00"))
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if en.tzinfo is None:
                en = en.replace(tzinfo=timezone.utc)
            busy.append({"start": s, "end": en, "source": "calendar"})
        except Exception:
            pass

    # Existing bookings
    bookings = await db.calendar_bookings.find(
        {
            "$or": [{"host_user_id": user_id}, {"guest_user_id": user_id}],
            "start": {"$gte": start_date, "$lte": end_date},
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0, "start": 1, "end": 1},
    ).to_list(200)
    for b in bookings:
        try:
            s = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
            en = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if en.tzinfo is None:
                en = en.replace(tzinfo=timezone.utc)
            busy.append({"start": s, "end": en, "source": "booking"})
        except Exception:
            pass

    # Existing interviews
    interviews = await db.interview_bookings.find(
        {
            "$or": [{"employer_id": user_id}, {"candidate_id": user_id}],
            "scheduled_start": {"$gte": start_date, "$lte": end_date},
            "status": {"$nin": ["cancelled"]},
        },
        {"_id": 0, "scheduled_start": 1, "scheduled_end": 1},
    ).to_list(200)
    for iv in interviews:
        try:
            s = datetime.fromisoformat(iv["scheduled_start"].replace("Z", "+00:00"))
            en = datetime.fromisoformat(iv["scheduled_end"].replace("Z", "+00:00"))
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if en.tzinfo is None:
                en = en.replace(tzinfo=timezone.utc)
            busy.append({"start": s, "end": en, "source": "interview"})
        except Exception:
            pass

    return busy


def _find_available_slots(
    emp_busy: list,
    cand_busy: list,
    start_date: datetime,
    days_ahead: int,
    work_start_hour: int = 9,
    work_end_hour: int = 18,
    duration_minutes: int = 45,
    buffer_minutes: int = 15,
) -> list:
    """Find mutually available interview slots."""
    all_busy = emp_busy + cand_busy
    slots = []

    for day_offset in range(days_ahead):
        day = start_date + timedelta(days=day_offset)
        if day.weekday() >= 5:  # Skip weekends
            continue

        for hour in range(work_start_hour, work_end_hour):
            for minute in [0, 30]:
                slot_start = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                if slot_end.hour > work_end_hour:
                    continue
                if slot_start <= datetime.now(timezone.utc) + timedelta(hours=2):
                    continue

                # Check conflicts with buffer
                buffered_start = slot_start - timedelta(minutes=buffer_minutes)
                buffered_end = slot_end + timedelta(minutes=buffer_minutes)

                conflict = False
                for busy in all_busy:
                    if buffered_start < busy["end"] and buffered_end > busy["start"]:
                        conflict = True
                        break

                if not conflict:
                    slots.append(
                        {
                            "start": slot_start.isoformat(),
                            "end": slot_end.isoformat(),
                            "date": slot_start.strftime("%Y-%m-%d"),
                            "time": slot_start.strftime("%H:%M"),
                            "day_name": slot_start.strftime("%A"),
                            "duration_minutes": duration_minutes,
                        }
                    )

        if len(slots) >= 20:
            break

    return slots[:20]


@router.post("/suggest-slots")
async def suggest_interview_slots(request: Request):
    """Smart Scheduler: Auto-detect availability and suggest optimal interview slots."""
    user = await require_auth(request)
    body = await request.json()
    candidate_id = body.get("candidate_id", "")
    employer_id = body.get("employer_id", user.user_id)
    duration = body.get("duration_minutes", 45)
    days_ahead = body.get("days_ahead", 7)
    work_start = body.get("work_start_hour", 9)
    work_end = body.get("work_end_hour", 18)

    if not candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id required")

    now = datetime.now(timezone.utc)
    start_date_str = now.isoformat()
    end_date_str = (now + timedelta(days=days_ahead)).isoformat()

    emp_busy = await _get_user_busy_slots(employer_id, start_date_str, end_date_str)
    cand_busy = await _get_user_busy_slots(candidate_id, start_date_str, end_date_str)

    slots = _find_available_slots(
        emp_busy,
        cand_busy,
        now.replace(tzinfo=timezone.utc),
        days_ahead,
        work_start,
        work_end,
        duration,
    )

    # AI rank the slots by optimality
    if slots and EMERGENT_KEY:
        slot_data = json.dumps(slots[:10])
        ai_resp = await _ai(
            "You are a scheduling optimizer. Rank these interview slots by optimality. Prefer mid-morning and early afternoon. Return JSON array of slot indices (0-based) in order of preference, with a brief reason for the top pick.",
            f'Rank these slots:\n{slot_data}\n\nReturn JSON: {{"ranked_indices": [0,2,1,...], "top_reason": "why the top slot is best"}}',
        )
        try:
            ranking = _parse_json(ai_resp)
            ranked_indices = ranking.get("ranked_indices", list(range(len(slots))))
            ranked_slots = [slots[i] for i in ranked_indices if i < len(slots)]
            for i, s in enumerate(ranked_slots):
                s["rank"] = i + 1
                s["ai_recommended"] = i == 0
            slots = ranked_slots
            top_reason = ranking.get("top_reason", "")
        except Exception:
            top_reason = ""
            for i, s in enumerate(slots):
                s["rank"] = i + 1
    else:
        top_reason = ""

    return {
        "slots": slots,
        "total": len(slots),
        "employer_busy_count": len(emp_busy),
        "candidate_busy_count": len(cand_busy),
        "ai_recommendation": top_reason,
        "duration_minutes": duration,
    }


@router.post("/quick-schedule")
async def quick_schedule_from_slot(request: Request):
    """One-click schedule from a suggested slot."""
    user = await require_auth(request)
    body = await request.json()
    candidate_id = body.get("candidate_id", "")
    job_id = body.get("job_id", "")
    slot_start = body.get("start", "")
    slot_end = body.get("end", "")
    interview_type = body.get("interview_type", "video")
    notes = body.get("notes", "")
    pipeline_id = body.get("pipeline_id", "")

    if not all([candidate_id, job_id, slot_start]):
        raise HTTPException(status_code=400, detail="candidate_id, job_id, and start required")

    candidate = await db.users.find_one({"user_id": candidate_id}, {"_id": 0, "name": 1, "email": 1})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0, "title": 1, "company_name": 1})

    now = datetime.now(timezone.utc).isoformat()
    interview_id = f"intv_{uuid.uuid4().hex[:12]}"
    start_dt = datetime.fromisoformat(slot_start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(slot_end.replace("Z", "+00:00")) if slot_end else start_dt + timedelta(minutes=45)

    interview = {
        "interview_id": interview_id,
        "application_id": "",
        "pipeline_id": pipeline_id,
        "job_id": job_id,
        "job_title": (job or {}).get("title", ""),
        "company_name": (job or {}).get("company_name", ""),
        "candidate_id": candidate_id,
        "candidate_name": candidate.get("name", ""),
        "candidate_email": candidate.get("email", ""),
        "employer_id": user.user_id,
        "employer_name": user.name,
        "interviewer_name": user.name,
        "interviewer_email": user.email,
        "interview_type": interview_type,
        "status": "scheduled",
        "scheduled_start": start_dt.isoformat(),
        "scheduled_end": end_dt.isoformat(),
        "timezone": "UTC",
        "duration_minutes": int((end_dt - start_dt).total_seconds() / 60),
        "location": None,
        "notes": notes,
        "meeting_link": f"https://meet.realaicoach.app/{interview_id}"
        if interview_type in ["video", "audio"]
        else None,
        "feedback": None,
        "reschedule_history": [],
        "reminder_sent_24h": False,
        "reminder_sent_1h": False,
        "reminder_sent_15m": False,
        "scheduled_via": "smart_scheduler",
        "created_at": now,
        "updated_at": now,
    }

    await db.interview_bookings.insert_one({**interview})
    await ws_manager.send_to_user(
        candidate_id,
        {
            "type": "interview_update",
            "event": "interview_scheduled",
            "data": {
                "interview_id": interview_id,
                "job_title": interview["job_title"],
                "date": start_dt.strftime("%Y-%m-%d"),
                "time": start_dt.strftime("%H:%M"),
            },
        },
    )
    await push_admin_alert(
        "interview_scheduled", "Smart Schedule", f"AI scheduled interview: {interview['job_title']}", "info"
    )

    return {"interview": interview, "success": True, "scheduled_via": "smart_scheduler"}


# ═══════════════════════════════════════════════════════════════
# PLATFORM AUTOMATION ENGINE
# ═══════════════════════════════════════════════════════════════


async def send_interview_reminders():
    """Background job: Send interview reminders at 24h, 1h, 15m tiers."""
    now = datetime.now(timezone.utc)
    tiers = [
        ("24h", 1410, 1470, "reminder_sent_24h"),
        ("1h", 50, 75, "reminder_sent_1h"),
        ("15m", 5, 20, "reminder_sent_15m"),
    ]

    total_sent = 0
    for label, min_min, max_min, flag in tiers:
        window_start = (now + timedelta(minutes=min_min)).isoformat()
        window_end = (now + timedelta(minutes=max_min)).isoformat()

        interviews = await db.interview_bookings.find(
            {
                "status": {"$in": ["scheduled", "confirmed"]},
                "scheduled_start": {"$gte": window_start, "$lte": window_end},
                flag: {"$ne": True},
            },
            {"_id": 0},
        ).to_list(100)

        for iv in interviews:
            # Notify candidate via WebSocket
            await ws_manager.send_to_user(
                iv["candidate_id"],
                {
                    "type": "interview_reminder",
                    "tier": label,
                    "data": {
                        "interview_id": iv["interview_id"],
                        "job_title": iv["job_title"],
                        "time": iv["scheduled_start"],
                        "meeting_link": iv.get("meeting_link"),
                    },
                },
            )
            # Notify employer via WebSocket
            await ws_manager.send_to_user(
                iv["employer_id"],
                {
                    "type": "interview_reminder",
                    "tier": label,
                    "data": {
                        "interview_id": iv["interview_id"],
                        "candidate_name": iv["candidate_name"],
                        "time": iv["scheduled_start"],
                    },
                },
            )

            # Send email reminders using interview_reminder template
            try:
                from utils.email_service import send_catalog_template, is_email_configured
                if is_email_configured():
                    minutes_map = {"24h": 1440, "1h": 60, "15m": 15}
                    mins = minutes_map.get(label, 60)
                    sched = iv.get("scheduled_start", "")
                    date_str = sched[:10] if sched else ""
                    time_str = sched[11:16] if len(sched) > 16 else ""

                    # Email to candidate
                    cand = await db.users.find_one({"user_id": iv["candidate_id"]}, {"_id": 0, "email": 1, "name": 1})
                    if cand and cand.get("email"):
                        await send_catalog_template(
                            recipient_email=cand["email"],
                            template_key="interview_reminder",
                            candidate_name=cand.get("name", ""),
                            job_title=iv.get("job_title", ""),
                            interviewer_name=iv.get("employer_name", iv.get("employer_id", "")),
                            interview_time=time_str,
                            interview_date=date_str,
                            minutes_until=mins,
                        )

                    # Email to employer
                    emp = await db.users.find_one({"user_id": iv["employer_id"]}, {"_id": 0, "email": 1, "name": 1})
                    if emp and emp.get("email"):
                        await send_catalog_template(
                            recipient_email=emp["email"],
                            template_key="interview_reminder",
                            candidate_name=emp.get("name", ""),
                            job_title=iv.get("job_title", ""),
                            interviewer_name=iv.get("candidate_name", ""),
                            interview_time=time_str,
                            interview_date=date_str,
                            minutes_until=mins,
                        )
            except Exception as e:
                logger.warning(f"Interview reminder email failed: {e}")

            await db.interview_bookings.update_one(
                {"interview_id": iv["interview_id"]},
                {"$set": {flag: True}},
            )
            total_sent += 1

    if total_sent:
        logger.info(f"Sent {total_sent} interview reminder(s)")


async def send_daily_job_suggestions():
    """Background job: Send daily AI job suggestions to candidates."""
    now = datetime.now(timezone.utc)
    logger.info("Running daily job suggestions...")

    profiles = await db.employee_profiles.find(
        {"skills": {"$exists": True, "$ne": []}}, {"_id": 0, "user_id": 1, "skills": 1, "preferred_industry": 1}
    ).to_list(100)

    active_jobs = await db.jobs.find(
        {"status": "active"}, {"_id": 0, "job_id": 1, "title": 1, "skills": 1, "company_name": 1}
    ).to_list(50)

    for profile in profiles:
        user_skills = set(s.lower() for s in profile.get("skills", []))
        matched_jobs = []
        for job in active_jobs:
            job_skills = set(s.lower() for s in job.get("skills", []))
            overlap = user_skills & job_skills
            if overlap:
                matched_jobs.append(
                    {
                        "job_id": job["job_id"],
                        "title": job["title"],
                        "company": job.get("company_name", ""),
                        "matching_skills": list(overlap),
                    }
                )

        if matched_jobs:
            await ws_manager.send_to_user(
                profile["user_id"],
                {
                    "type": "daily_job_suggestions",
                    "data": {"jobs": matched_jobs[:5], "date": now.strftime("%Y-%m-%d")},
                },
            )
            await db.daily_suggestions.insert_one(
                {
                    "user_id": profile["user_id"],
                    "jobs": matched_jobs[:5],
                    "sent_at": now.isoformat(),
                }
            )

    logger.info(f"Sent daily suggestions to {len(profiles)} candidates")


async def detect_hiring_delays():
    """Background job: Detect stalled hiring pipelines and send alerts."""
    now = datetime.now(timezone.utc)
    stale_threshold = (now - timedelta(days=7)).isoformat()

    stale_pipelines = await db.hiring_pipeline.find(
        {
            "status": "active",
            "updated_at": {"$lt": stale_threshold},
            "current_stage": {"$nin": ["offer_recommendation"]},
        },
        {"_id": 0},
    ).to_list(100)

    for pipe in stale_pipelines:
        await ws_manager.send_to_user(
            pipe.get("employer_id", ""),
            {
                "type": "hiring_delay_alert",
                "data": {
                    "pipeline_id": pipe["pipeline_id"],
                    "candidate_name": pipe.get("candidate_name", ""),
                    "job_title": pipe.get("job_title", ""),
                    "current_stage": pipe.get("current_stage", ""),
                    "days_stale": 7,
                },
            },
        )

    if stale_pipelines:
        await push_admin_alert(
            "hiring_delay",
            "Hiring Delays Detected",
            f"{len(stale_pipelines)} pipeline(s) stalled for 7+ days",
            "warning",
        )
        logger.info(f"Detected {len(stale_pipelines)} stale hiring pipelines")


async def notify_employers_new_candidates():
    """Background job: Notify employers of new candidate applications in last 24h."""
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(hours=24)).isoformat()

    recent_apps = await db.job_applications.find(
        {"applied_at": {"$gte": yesterday}}, {"_id": 0, "job_id": 1, "user_id": 1}
    ).to_list(200)

    job_apps = {}
    for app in recent_apps:
        jid = app["job_id"]
        if jid not in job_apps:
            job_apps[jid] = []
        job_apps[jid].append(app["user_id"])

    for job_id, candidates in job_apps.items():
        job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0, "poster_user_id": 1, "title": 1})
        if job:
            await ws_manager.send_to_user(
                job["poster_user_id"],
                {
                    "type": "new_candidates_alert",
                    "data": {
                        "job_id": job_id,
                        "job_title": job.get("title", ""),
                        "new_candidates_count": len(candidates),
                    },
                },
            )


# ═══════════════════════════════════════════════════════════════
# ADMIN AI OVERSIGHT DASHBOARD
# ═══════════════════════════════════════════════════════════════


@router.get("/admin/ai-oversight")
async def admin_ai_oversight(request: Request):
    """Admin: AI Oversight Dashboard with recruitment intelligence."""
    await require_admin(request)

    total_pipelines = await db.hiring_pipeline.count_documents({})
    active_pipelines = await db.hiring_pipeline.count_documents({"status": "active"})
    completed_pipelines = await db.hiring_pipeline.count_documents({"current_stage": "offer_recommendation"})

    # AI decision accuracy (based on feedback after hire)
    pipelines_with_pred = await db.hiring_pipeline.find(
        {"prediction": {"$ne": None}}, {"_id": 0, "prediction": 1}
    ).to_list(500)

    decisions = {"strong_hire": 0, "hire": 0, "maybe": 0, "pass": 0}
    confidence_scores = []
    for p in pipelines_with_pred:
        pred = p.get("prediction", {})
        d = pred.get("decision", "")
        if d in decisions:
            decisions[d] += 1
        hc = pred.get("hire_confidence")
        if hc:
            confidence_scores.append(hc)

    avg_confidence = round(sum(confidence_scores) / max(len(confidence_scores), 1), 1)

    # Employer activity scores
    emp_pipeline = [
        {"$group": {"_id": "$employer_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    emp_activity = await db.interview_bookings.aggregate(emp_pipeline).to_list(10)
    for ea in emp_activity:
        u = await db.users.find_one({"user_id": ea["_id"]}, {"_id": 0, "name": 1, "email": 1})
        ea["name"] = (u or {}).get("name", "Unknown")
        ea["email"] = (u or {}).get("email", "")

    # Candidate engagement
    total_profiles = await db.employee_profiles.count_documents({})
    active_candidates = await db.job_applications.distinct("user_id")
    engagement_rate = round(len(active_candidates) / max(total_profiles, 1) * 100, 1)

    # Interview metrics
    total_interviews = await db.interview_bookings.count_documents({})
    completed_interviews = await db.interview_bookings.count_documents({"status": "completed"})
    cancelled_interviews = await db.interview_bookings.count_documents({"status": "cancelled"})

    # Hiring funnel
    total_apps = await db.job_applications.count_documents({})
    funnel = {
        "applications": total_apps,
        "screened": await db.hiring_pipeline.count_documents({"current_stage": {"$nin": ["application_received"]}}),
        "interviewed": completed_interviews,
        "offered": await db.hiring_pipeline.count_documents({"current_stage": "offer_recommendation"}),
        "hired": decisions.get("strong_hire", 0) + decisions.get("hire", 0),
    }

    # Stale pipelines
    stale_threshold = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stale_count = await db.hiring_pipeline.count_documents(
        {
            "status": "active",
            "updated_at": {"$lt": stale_threshold},
            "current_stage": {"$nin": ["offer_recommendation"]},
        }
    )

    # Daily suggestions sent
    suggestions_sent = await db.daily_suggestions.count_documents({})

    # Smart schedules
    smart_scheduled = await db.interview_bookings.count_documents({"scheduled_via": "smart_scheduler"})

    return {
        "ai_overview": {
            "total_pipelines": total_pipelines,
            "active_pipelines": active_pipelines,
            "completed_pipelines": completed_pipelines,
            "avg_hire_confidence": avg_confidence,
            "ai_decisions": decisions,
            "stale_pipelines": stale_count,
        },
        "employer_activity": {
            "top_employers": [
                {"name": e.get("name"), "email": e.get("email"), "interviews": e["count"]} for e in emp_activity
            ],
        },
        "candidate_engagement": {
            "total_profiles": total_profiles,
            "active_candidates": len(active_candidates),
            "engagement_rate": engagement_rate,
        },
        "interview_metrics": {
            "total": total_interviews,
            "completed": completed_interviews,
            "cancelled": cancelled_interviews,
            "completion_rate": round(completed_interviews / max(total_interviews, 1) * 100, 1),
            "smart_scheduled": smart_scheduled,
        },
        "hiring_funnel": funnel,
        "automation": {
            "daily_suggestions_sent": suggestions_sent,
            "interview_reminders_active": True,
            "hiring_delay_detection": True,
        },
    }


@router.post("/admin/override-decision/{pipeline_id}")
async def admin_override_decision(pipeline_id: str, request: Request):
    """Admin: Override AI hiring decision."""
    await require_admin(request)
    body = await request.json()
    new_decision = body.get("decision", "")
    reason = body.get("reason", "")

    if new_decision not in ["strong_hire", "hire", "maybe", "pass"]:
        raise HTTPException(status_code=400, detail="Invalid decision")

    pipe = await db.hiring_pipeline.find_one({"pipeline_id": pipeline_id}, {"_id": 0})
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    now = datetime.now(timezone.utc).isoformat()
    old_decision = (pipe.get("prediction") or {}).get("decision", "unknown")

    await db.hiring_pipeline.update_one(
        {"pipeline_id": pipeline_id},
        {
            "$set": {
                "prediction.decision": new_decision,
                "prediction.admin_override": True,
                "prediction.override_reason": reason,
                "prediction.override_at": now,
                "prediction.original_decision": old_decision,
                "updated_at": now,
            }
        },
    )

    await push_admin_alert(
        "decision_override",
        "AI Decision Overridden",
        f"Pipeline {pipeline_id}: {old_decision} -> {new_decision}. Reason: {reason}",
        "warning",
    )

    return {"success": True, "old_decision": old_decision, "new_decision": new_decision}


# Manual trigger for automation tasks
@router.post("/admin/trigger-automation/{task}")
async def admin_trigger_automation(task: str, request: Request):
    """Admin: Manually trigger an automation task."""
    await require_admin(request)

    if task == "interview_reminders":
        await send_interview_reminders()
        return {"success": True, "task": task, "message": "Interview reminders sent"}
    elif task == "daily_suggestions":
        await send_daily_job_suggestions()
        return {"success": True, "task": task, "message": "Daily suggestions sent"}
    elif task == "hiring_delays":
        await detect_hiring_delays()
        return {"success": True, "task": task, "message": "Hiring delay check complete"}
    elif task == "new_candidates":
        await notify_employers_new_candidates()
        return {"success": True, "task": task, "message": "New candidate notifications sent"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task: {task}")
