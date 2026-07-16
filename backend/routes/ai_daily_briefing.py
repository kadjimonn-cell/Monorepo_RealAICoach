"""AI Daily Briefing — Personalized morning dashboard with AI-curated content.

Aggregates tasks, reminders, industry news, learning picks, and coaching insights.

API:
- GET  /api/ai-briefing/today     — Today's personalized briefing
- GET  /api/ai-briefing/history   — Past briefings
- GET  /api/ai-briefing/preferences — Read briefing preferences
- POST /api/ai-briefing/preferences — Update briefing preferences
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-briefing")


class BriefingPreferences(BaseModel):
    interests: Optional[List[str]] = None
    industry: Optional[str] = None
    briefing_time: Optional[str] = None
    include_news: Optional[bool] = None
    include_tips: Optional[bool] = None
    include_motivation: Optional[bool] = None


DEFAULT_BRIEFING_PREFERENCES = {
    "interests": ["career development", "productivity"],
    "industry": "technology",
    "briefing_time": "08:00",
    "include_news": True,
    "include_tips": True,
    "include_motivation": True,
}


@router.get("/preferences")
async def get_preferences(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    doc = await db.briefing_preferences.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    merged = {**DEFAULT_BRIEFING_PREFERENCES}
    merged.update({k: v for k, v in doc.items() if v is not None})
    merged["interests"] = merged.get("interests") or []
    if not isinstance(merged["interests"], list):
        merged["interests"] = []
    return merged


@router.get("/today")
async def get_today_briefing(request: Request, force: bool = False):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    uid = user.user_id
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check if already generated today
    existing = await db.ai_briefings.find_one({"user_id": uid, "date": today}, {"_id": 0})
    if existing and not force:
        return existing

    # Gather user context
    prefs = await db.briefing_preferences.find_one({"user_id": uid}, {"_id": 0}) or {}
    interests = prefs.get("interests", ["career development", "productivity"])
    industry = prefs.get("industry", "technology")

    # Get user's active goals
    goals = (
        await db.ai_goals.find({"user_id": uid, "status": "active"}, {"_id": 0, "title": 1, "progress": 1})
        .limit(5)
        .to_list(5)
    )
    goals_text = "\n".join([f"- {g['title']} ({g['progress']}%)" for g in goals]) or "No active goals"

    # Get recent coaching sessions
    recent_coach = (
        await db.coach_conversations.find({"user_id": uid}, {"_id": 0, "title": 1, "topic_name": 1})
        .sort("updated_at", -1)
        .limit(3)
        .to_list(3)
    )
    coach_text = "\n".join([f"- {c['title']} ({c['topic_name']})" for c in recent_coach]) or "No recent sessions"

    # Get user stats
    total_sessions = await db.conversations.count_documents({"user_id": uid})

    system_msg = """You are a Personal AI Briefing Generator. Create a personalized daily briefing.
Return ONLY valid JSON:
{
  "greeting": "Good morning, [Name]! Here's your briefing for today.",
  "weather_mood": "energetic|focused|calm|motivated",
  "top_priorities": [
    {"title": "Priority 1", "description": "Why it matters", "action": "Specific next step"},
    {"title": "Priority 2", "description": "Why", "action": "Step"}
  ],
  "learning_picks": [
    {"title": "Topic to learn", "description": "Why relevant", "estimated_time": "15 min"},
    {"title": "Topic 2", "description": "Why", "estimated_time": "10 min"}
  ],
  "industry_insights": [
    {"headline": "Industry insight", "summary": "Brief summary", "relevance": "Why it matters to them"}
  ],
  "motivation": "An inspiring, personalized motivational message",
  "wellness_tip": "A practical wellness or productivity tip for today",
  "fun_fact": "An interesting fact related to their interests"
}"""

    prompt = f"""User: {getattr(user, "name", "User")}
Industry: {industry}
Interests: {", ".join(interests)}
Active Goals:
{goals_text}
Recent Coaching:
{coach_text}
Total sessions: {total_sessions}
Date: {today}

Generate a personalized, engaging daily briefing:"""

    try:
        briefing_data = await ai_generate_json(system_msg, prompt, f"briefing-{uid[:8]}")
    except Exception as e:
        logger.error(f"Briefing generation error: {e}")
        primary_goal = goals[0] if goals else None
        primary_session = recent_coach[0] if recent_coach else None
        top_priorities = []
        if primary_goal:
            top_priorities.append(
                {
                    "title": str(primary_goal.get("title") or "Primary active goal"),
                    "description": f"Current progress: {int(primary_goal.get('progress') or 0)}%",
                    "action": "Review this goal and schedule your next focused step.",
                }
            )
        if primary_session:
            session_title = str(primary_session.get("title") or primary_session.get("topic_name") or "Recent coaching session")
            top_priorities.append(
                {
                    "title": "Convert coaching insight to action",
                    "description": f"Most recent coaching context: {session_title}",
                    "action": "Capture one execution step from this session and complete it today.",
                }
            )

        learning_picks = []
        for item in recent_coach[:2]:
            topic = str(item.get("topic_name") or item.get("title") or "Coaching topic")
            learning_picks.append(
                {
                    "title": topic,
                    "description": "Derived from your recent coaching activity.",
                    "estimated_time": "10 min",
                }
            )

        motivation = (
            f"You have completed {total_sessions} coaching sessions. "
            "Use that momentum to execute one high-impact action today."
        )

        briefing_data = {
            "greeting": f"Good morning, {getattr(user, 'name', 'there')}! Here is your platform-data briefing for {today}.",
            "weather_mood": "motivated",
            "top_priorities": top_priorities,
            "learning_picks": learning_picks,
            "industry_insights": [],
            "motivation": motivation,
            "wellness_tip": None,
            "fun_fact": None,
        }

    briefing_data = briefing_data if isinstance(briefing_data, dict) else {}
    top_priorities = briefing_data.get("top_priorities") if isinstance(briefing_data.get("top_priorities"), list) else []
    learning_picks = briefing_data.get("learning_picks") if isinstance(briefing_data.get("learning_picks"), list) else []
    industry_insights = briefing_data.get("industry_insights") if isinstance(briefing_data.get("industry_insights"), list) else []

    now = datetime.now(timezone.utc).isoformat()
    briefing = {
        "briefing_id": f"brief_{uuid.uuid4().hex[:12]}",
        "user_id": uid,
        "date": today,
        **briefing_data,
        "top_priorities": top_priorities,
        "learning_picks": learning_picks,
        "industry_insights": industry_insights,
        "goals_snapshot": goals,
        "created_at": now,
    }

    if existing:
        await db.ai_briefings.update_one(
            {"user_id": uid, "date": today},
            {"$set": {k: v for k, v in briefing.items() if k != "user_id"}},
            upsert=True,
        )
    else:
        await db.ai_briefings.insert_one({**briefing})

    briefing.pop("_id", None)
    return briefing


@router.get("/history")
async def get_briefing_history(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    briefings = (
        await db.ai_briefings.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(14).to_list(14)
    )
    return {"briefings": briefings}


@router.post("/preferences")
async def update_preferences(request: Request, body: BriefingPreferences):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    update = {k: v for k, v in body.dict().items() if v is not None}
    if update:
        await db.briefing_preferences.update_one(
            {"user_id": user.user_id},
            {"$set": {**update, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )

    latest = await db.briefing_preferences.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    merged = {**DEFAULT_BRIEFING_PREFERENCES}
    merged.update({k: v for k, v in latest.items() if v is not None})
    merged["interests"] = merged.get("interests") or []
    if not isinstance(merged["interests"], list):
        merged["interests"] = []
    return {"success": True, "preferences": merged}
