"""Smart Onboarding & Onboarding Analytics API."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from .db import db, require_auth

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

ONBOARDING_STEPS = [
    {"id": "welcome", "label": "Welcome Tour", "order": 1},
    {"id": "discover", "label": "Job Discovery", "order": 2},
    {"id": "hiring", "label": "AI Hiring", "order": 3},
    {"id": "employer", "label": "Jobs Portal", "order": 4},
    {"id": "coach", "label": "Interview Coach", "order": 5},
    {"id": "mock", "label": "Mock Interview", "order": 6},
    {"id": "docs", "label": "Collab Docs", "order": 7},
    {"id": "profile", "label": "Complete Profile", "order": 8},
    {"id": "first_search", "label": "First Job Search", "order": 9},
]


class OnboardingProgress(BaseModel):
    step_id: str
    completed: bool = True


class OnboardingDismiss(BaseModel):
    dismissed: bool = True


@router.get("/steps")
async def get_onboarding_steps():
    return {"steps": ONBOARDING_STEPS}


@router.get("/progress")
async def get_user_progress(request: Request):
    user = await require_auth(request)
    uid = user.user_id
    doc = await db.onboarding_progress.find_one({"user_id": uid}, {"_id": 0})
    if not doc:
        doc = {"user_id": uid, "completed_steps": [], "dismissed": False, "started_at": None, "completed_at": None}
    return doc


@router.post("/progress")
async def update_progress(data: OnboardingProgress, request: Request):
    user = await require_auth(request)
    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    doc = await db.onboarding_progress.find_one({"user_id": uid}, {"_id": 0})
    if not doc:
        doc = {"user_id": uid, "completed_steps": [], "dismissed": False, "started_at": now, "completed_at": None}
        await db.onboarding_progress.insert_one({**doc, "started_at": now})
    completed = doc.get("completed_steps", [])
    if data.step_id not in completed and data.completed:
        completed.append(data.step_id)
    all_done = len(completed) >= len(ONBOARDING_STEPS)
    await db.onboarding_progress.update_one(
        {"user_id": uid},
        {"$set": {"completed_steps": completed, "updated_at": now, "completed_at": now if all_done else None}},
        upsert=True,
    )
    return {"success": True, "completed_steps": completed, "all_done": all_done}


@router.post("/dismiss")
async def dismiss_onboarding(data: OnboardingDismiss, request: Request):
    user = await require_auth(request)
    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    await db.onboarding_progress.update_one(
        {"user_id": uid},
        {"$set": {"dismissed": data.dismissed, "updated_at": now}},
        upsert=True,
    )
    return {"success": True}


@router.get("/analytics")
async def get_onboarding_analytics(request: Request):
    """Executive-level onboarding funnel analytics."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    total_users = await db.users.count_documents({})
    pipeline_started = [{"$match": {"started_at": {"$ne": None}}}, {"$group": {"_id": None, "count": {"$sum": 1}}}]
    started_result = await db.onboarding_progress.aggregate(pipeline_started).to_list(1)
    started_count = started_result[0]["count"] if started_result else 0
    pipeline_completed = [{"$match": {"completed_at": {"$ne": None}}}, {"$group": {"_id": None, "count": {"$sum": 1}}}]
    completed_result = await db.onboarding_progress.aggregate(pipeline_completed).to_list(1)
    completed_count = completed_result[0]["count"] if completed_result else 0
    pipeline_dismissed = [{"$match": {"dismissed": True}}, {"$group": {"_id": None, "count": {"$sum": 1}}}]
    dismissed_result = await db.onboarding_progress.aggregate(pipeline_dismissed).to_list(1)
    dismissed_count = dismissed_result[0]["count"] if dismissed_result else 0
    # Step-by-step funnel
    step_funnel = []
    for step in ONBOARDING_STEPS:
        count = await db.onboarding_progress.count_documents({"completed_steps": step["id"]})
        step_funnel.append(
            {
                "step_id": step["id"],
                "label": step["label"],
                "count": count,
                "rate": round(count / max(started_count, 1) * 100, 1),
            }
        )
    # Recent 7-day trend
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_starts = await db.onboarding_progress.count_documents({"started_at": {"$gte": seven_days_ago}})
    recent_completes = await db.onboarding_progress.count_documents({"completed_at": {"$gte": seven_days_ago}})
    # Avg completion time
    pipeline_avg = [{"$match": {"completed_at": {"$ne": None}, "started_at": {"$ne": None}}}, {"$limit": 100}]
    completions = await db.onboarding_progress.aggregate(pipeline_avg).to_list(100)
    avg_mins = 0
    if completions:
        durations = []
        for c in completions:
            try:
                s = datetime.fromisoformat(c["started_at"].replace("Z", "+00:00"))
                e = datetime.fromisoformat(c["completed_at"].replace("Z", "+00:00"))
                durations.append((e - s).total_seconds() / 60)
            except Exception:
                pass
        if durations:
            avg_mins = round(sum(durations) / len(durations), 1)

    return {
        "total_users": total_users,
        "started": started_count,
        "completed": completed_count,
        "dismissed": dismissed_count,
        "activation_rate": round(completed_count / max(total_users, 1) * 100, 1),
        "completion_rate": round(completed_count / max(started_count, 1) * 100, 1),
        "drop_off_rate": round(dismissed_count / max(started_count, 1) * 100, 1),
        "avg_completion_minutes": avg_mins,
        "step_funnel": step_funnel,
        "recent_7d": {"starts": recent_starts, "completions": recent_completes},
    }
