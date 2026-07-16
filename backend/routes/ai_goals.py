"""AI Goal Tracker & Planner — Set goals, get AI milestones, track progress.

AI breaks goals into milestones, provides weekly reviews, and adapts recommendations.

API:
- GET  /api/ai-goals             — User's goals
- POST /api/ai-goals             — Create a new goal with AI milestones
- GET  /api/ai-goals/{id}        — Get goal details
- PUT  /api/ai-goals/{id}/milestones/{mid} — Update milestone status
- POST /api/ai-goals/{id}/review — AI weekly review
- GET  /api/ai-goals/stats       — Goal statistics
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate_json, ai_generate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-goals")


class CreateGoal(BaseModel):
    title: str
    description: str
    category: str = "personal"
    target_date: Optional[str] = None


class UpdateMilestone(BaseModel):
    status: str  # pending, in_progress, completed, skipped


@router.get("/stats")
async def get_goal_stats(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    uid = user.user_id
    total = await db.ai_goals.count_documents({"user_id": uid})
    active = await db.ai_goals.count_documents({"user_id": uid, "status": "active"})
    completed = await db.ai_goals.count_documents({"user_id": uid, "status": "completed"})

    # Streak: consecutive days with milestone completions
    streak = 0
    today = datetime.now(timezone.utc).date()
    for i in range(60):
        day = (today - timedelta(days=i)).isoformat()
        next_day = (today - timedelta(days=i - 1)).isoformat() if i > 0 else (today + timedelta(days=1)).isoformat()
        count = await db.ai_goal_events.count_documents(
            {"user_id": uid, "event_type": "milestone_completed", "created_at": {"$gte": day, "$lt": next_day}}
        )
        if count > 0:
            streak += 1
        else:
            if i > 0:
                break
    return {"total": total, "active": active, "completed": completed, "streak": streak}


@router.get("")
async def get_goals(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    goals = await db.ai_goals.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"goals": goals}


@router.post("")
async def create_goal(request: Request, body: CreateGoal):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    system_msg = """You are a Goal Planning Expert. Break down the user's goal into 5-7 actionable milestones.
Return ONLY valid JSON:
{
  "milestones": [
    {"id": 1, "title": "Milestone title", "description": "Specific action steps", "timeframe": "Week 1", "priority": "high|medium|low", "tips": "Practical tip"},
    ...
  ],
  "quick_wins": ["Something they can do today", "Another quick start"],
  "potential_obstacles": ["Obstacle 1"],
  "success_metrics": ["How to measure progress"]
}"""
    prompt = f"Goal: {body.title}\nDescription: {body.description}\nCategory: {body.category}\nTarget date: {body.target_date or 'flexible'}\nGenerate a detailed plan:"

    try:
        plan = await ai_generate_json(system_msg, prompt, f"goal-{user['user_id'][:8]}")
    except Exception as e:
        logger.error(f"Goal planning error: {e}")
        plan = {
            "milestones": [
                {
                    "id": 1,
                    "title": "Get started",
                    "description": "Begin with the first step",
                    "timeframe": "This week",
                    "priority": "high",
                    "tips": "Start small",
                }
            ],
            "quick_wins": ["Take the first step today"],
            "potential_obstacles": ["Procrastination"],
            "success_metrics": ["Track daily progress"],
        }

    now = datetime.now(timezone.utc).isoformat()
    milestones = []
    for m in plan.get("milestones", []):
        milestones.append({**m, "status": "pending", "completed_at": None})

    goal = {
        "goal_id": f"goal_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "title": body.title,
        "description": body.description,
        "category": body.category,
        "target_date": body.target_date,
        "status": "active",
        "progress": 0,
        "milestones": milestones,
        "quick_wins": plan.get("quick_wins", []),
        "potential_obstacles": plan.get("potential_obstacles", []),
        "success_metrics": plan.get("success_metrics", []),
        "reviews": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.ai_goals.insert_one(goal)
    goal.pop("_id", None)
    try:
        from utils.ws_manager import broadcast_data_change

        await broadcast_data_change("goals", "created", user.user_id)
    except Exception:
        pass
    return goal


@router.get("/{goal_id}")
async def get_goal(request: Request, goal_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    goal = await db.ai_goals.find_one({"goal_id": goal_id, "user_id": user.user_id}, {"_id": 0})
    if not goal:
        raise HTTPException(404, "Goal not found")
    return goal


@router.put("/{goal_id}/milestones/{milestone_id}")
async def update_milestone(request: Request, goal_id: str, milestone_id: int, body: UpdateMilestone):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    goal = await db.ai_goals.find_one({"goal_id": goal_id, "user_id": user.user_id}, {"_id": 0})
    if not goal:
        raise HTTPException(404, "Goal not found")

    now = datetime.now(timezone.utc).isoformat()
    milestones = goal.get("milestones", [])
    found = False
    for m in milestones:
        if m.get("id") == milestone_id:
            m["status"] = body.status
            if body.status == "completed":
                m["completed_at"] = now
            found = True
            break
    if not found:
        raise HTTPException(404, "Milestone not found")

    # Calculate progress
    total = len(milestones)
    completed = sum(1 for m in milestones if m.get("status") == "completed")
    progress = round((completed / total) * 100) if total > 0 else 0
    status = "completed" if progress == 100 else "active"

    await db.ai_goals.update_one(
        {"goal_id": goal_id},
        {"$set": {"milestones": milestones, "progress": progress, "status": status, "updated_at": now}},
    )

    if body.status == "completed":
        await db.ai_goal_events.insert_one(
            {
                "user_id": user.user_id,
                "goal_id": goal_id,
                "event_type": "milestone_completed",
                "milestone_id": milestone_id,
                "created_at": now,
            }
        )

    # Send notifications for goal completion or milestone progress
    try:
        from routes.notification_engine import emit_goal_completed, emit_goal_reminder

        if status == "completed":
            await emit_goal_completed(user.user_id, goal.get("title", "Untitled Goal"))
            # Send goal completed celebration email
            try:
                from utils.email_service import send_catalog_template, is_email_configured
                if is_email_configured():
                    await send_catalog_template(
                        recipient_email=user.email,
                        template_key="goal_completed",
                        recipient_name=user.name or user.email,
                        user_name=user.name or user.email,
                        goal_title=goal.get("title", "Untitled Goal"),
                        completed_at=now,
                    )
            except Exception:
                pass
        elif body.status == "completed" and progress >= 50 and progress < 100:
            await emit_goal_reminder(
                user.user_id,
                goal.get("title", "Untitled Goal"),
                message=f"Great progress! You're {progress}% done with your goal.",
            )
    except Exception as e:
        logger.error(f"Goal notification failed: {e}")

    try:
        from utils.ws_manager import broadcast_data_change

        await broadcast_data_change("goals", "updated", user.user_id)
    except Exception:
        pass
    return {"progress": progress, "status": status, "milestones": milestones}


@router.post("/{goal_id}/review")
async def ai_review(request: Request, goal_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    goal = await db.ai_goals.find_one({"goal_id": goal_id, "user_id": user.user_id}, {"_id": 0})
    if not goal:
        raise HTTPException(404, "Goal not found")

    milestones_summary = "\n".join([f"- {m['title']}: {m['status']}" for m in goal.get("milestones", [])])

    prompt = f"""Goal: {goal["title"]}
Description: {goal["description"]}
Progress: {goal["progress"]}%
Milestones:
{milestones_summary}

Provide an encouraging, specific progress review with next steps:"""

    try:
        review_text = await ai_generate(
            "You are an encouraging Goal Coach. Provide a brief, motivating progress review (3-4 sentences) with 2-3 specific next steps.",
            prompt,
            f"review-{goal_id}",
        )
    except Exception as e:
        logger.error(f"AI review error: {e}")
        review_text = f"You're at {goal['progress']}% — keep going! Focus on completing the next pending milestone."

    now = datetime.now(timezone.utc).isoformat()
    review = {"review_text": review_text, "progress_at_review": goal["progress"], "created_at": now}

    await db.ai_goals.update_one(
        {"goal_id": goal_id},
        {"$push": {"reviews": review}, "$set": {"updated_at": now}},
    )
    return review
