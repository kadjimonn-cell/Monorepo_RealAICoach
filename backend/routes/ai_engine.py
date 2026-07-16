"""Proactive AI Engine — Smart recommendations, context memory, engagement optimization.

Endpoints:
- GET  /api/ai-engine/recommendations        Personalized AI recommendations
- GET  /api/ai-engine/context/{user_id}       User AI context/memory
- POST /api/ai-engine/context/{user_id}       Update user AI context
- GET  /api/ai-engine/insights                AI-generated proactive insights
- POST /api/ai-engine/track-engagement        Track user engagement events
- GET  /api/ai-engine/engagement-score        User engagement score
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import uuid
import os
import logging

from .db import db, require_auth

router = APIRouter(prefix="/ai-engine")
logger = logging.getLogger("routes.ai_engine")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


@router.get("/recommendations")
async def get_recommendations(request: Request):
    """Generate personalized AI recommendations based on user activity."""
    user = await require_auth(request)
    uid = user.user_id
    now = datetime.now(timezone.utc)

    # Gather user context
    recent_sessions = (
        await db.practice_sessions.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    )

    recent_bookings = (
        await db.calendar_bookings.find({"user_id": uid}, {"_id": 0}).sort("start", -1).limit(3).to_list(3)
    )

    applications = (
        await db.applications.find({"user_id": uid}, {"_id": 0, "status": 1, "job_title": 1})
        .sort("applied_at", -1)
        .limit(5)
        .to_list(5)
    )

    progress = await db.user_progress.find_one({"user_id": uid}, {"_id": 0})

    # Build context-aware recommendations
    recommendations = []
    priority = 1

    # Practice recommendations
    if len(recent_sessions) == 0:
        recommendations.append(
            {
                "id": f"rec_{uuid.uuid4().hex[:8]}",
                "type": "practice",
                "priority": priority,
                "title": "Start Your Interview Practice",
                "description": "Begin with a mock interview to identify your strengths and areas for improvement.",
                "action_url": "/(tabs)/practice",
                "action_label": "Start Practice",
                "icon": "chatbubbles",
                "color": "#3B82F6",
                "ai_confidence": 0.95,
            }
        )
        priority += 1
    elif len(recent_sessions) < 3:
        recommendations.append(
            {
                "id": f"rec_{uuid.uuid4().hex[:8]}",
                "type": "practice",
                "priority": priority,
                "title": "Keep Building Momentum",
                "description": f"You've completed {len(recent_sessions)} practice sessions. Try to reach 5 this week for optimal improvement.",
                "action_url": "/(tabs)/practice",
                "action_label": "Continue Practice",
                "icon": "rocket",
                "color": "#10B981",
                "ai_confidence": 0.88,
            }
        )
        priority += 1

    # Career recommendations
    if len(applications) == 0:
        recommendations.append(
            {
                "id": f"rec_{uuid.uuid4().hex[:8]}",
                "type": "career",
                "priority": priority,
                "title": "Explore Job Opportunities",
                "description": "Our AI job matching can find roles perfectly suited to your skills and experience.",
                "action_url": "/hiring-hub",
                "action_label": "Browse Jobs",
                "icon": "briefcase",
                "color": "#6366F1",
                "ai_confidence": 0.90,
            }
        )
        priority += 1
    else:
        active = [a for a in applications if a.get("status") in ("applied", "in_review", "interviewing")]
        if active:
            recommendations.append(
                {
                    "id": f"rec_{uuid.uuid4().hex[:8]}",
                    "type": "career",
                    "priority": priority,
                    "title": f"{len(active)} Active Application{'s' if len(active) > 1 else ''}",
                    "description": "Stay prepared — practice interview questions for your pending applications.",
                    "action_url": "/hiring-hub",
                    "action_label": "View Applications",
                    "icon": "documents",
                    "color": "#F59E0B",
                    "ai_confidence": 0.92,
                }
            )
            priority += 1

    # Meeting recommendations
    upcoming = [b for b in recent_bookings if b.get("status") == "confirmed" and b.get("start", "") > now.isoformat()]
    if upcoming:
        recommendations.append(
            {
                "id": f"rec_{uuid.uuid4().hex[:8]}",
                "type": "meeting",
                "priority": priority,
                "title": f"Upcoming Meeting: {upcoming[0].get('guest_name', 'Guest')}",
                "description": f"Your next meeting is on {upcoming[0].get('start', '')[:10]}. Make sure to prepare your talking points.",
                "action_url": "/book-meeting",
                "action_label": "View Meeting",
                "icon": "calendar",
                "color": "#8B5CF6",
                "ai_confidence": 0.95,
            }
        )
        priority += 1

    # Engagement recommendations
    engagement = await db.ai_engagement.find_one({"user_id": uid}, {"_id": 0})
    if engagement:
        score = engagement.get("score", 0)
        if score < 40:
            recommendations.append(
                {
                    "id": f"rec_{uuid.uuid4().hex[:8]}",
                    "type": "engagement",
                    "priority": priority,
                    "title": "Boost Your Engagement",
                    "description": "Explore mini-apps and AI tools to maximize your platform experience.",
                    "action_url": "/mini-apps",
                    "action_label": "Explore Apps",
                    "icon": "apps",
                    "color": "#EC4899",
                    "ai_confidence": 0.85,
                }
            )
            priority += 1

    # Progress recommendations
    if progress:
        streak = progress.get("current_streak", 0)
        if streak >= 3:
            recommendations.append(
                {
                    "id": f"rec_{uuid.uuid4().hex[:8]}",
                    "type": "achievement",
                    "priority": priority,
                    "title": f"{streak}-Day Streak! Keep Going!",
                    "description": "Your consistency is paying off. The AI is learning your patterns for better coaching.",
                    "action_url": "/(tabs)/progress",
                    "action_label": "View Progress",
                    "icon": "flame",
                    "color": "#EF4444",
                    "ai_confidence": 0.90,
                }
            )
            priority += 1

    # AI content recommendation
    recommendations.append(
        {
            "id": f"rec_{uuid.uuid4().hex[:8]}",
            "type": "learning",
            "priority": priority + 5,
            "title": "AI Learning Path",
            "description": "Our AI has curated content based on your activity and goals. Check the Library for personalized resources.",
            "action_url": "/(tabs)/content-library",
            "action_label": "View Library",
            "icon": "book",
            "color": "#14B8A6",
            "ai_confidence": 0.80,
        }
    )

    recommendations.sort(key=lambda r: r["priority"])

    return {
        "recommendations": recommendations[:6],
        "generated_at": now.isoformat(),
        "context_factors": {
            "practice_sessions": len(recent_sessions),
            "active_applications": len(applications),
            "upcoming_meetings": len(upcoming) if "upcoming" in dir() else 0,
        },
    }


@router.get("/context/{user_id}")
async def get_ai_context(user_id: str, request: Request):
    """Get stored AI context/memory for a user."""
    user = await require_auth(request)
    if user.user_id != user_id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Access denied")

    ctx = await db.ai_context.find_one({"user_id": user_id}, {"_id": 0})
    if not ctx:
        ctx = {
            "user_id": user_id,
            "preferences": {},
            "conversation_history": [],
            "skill_profile": {},
            "goals": [],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    return ctx


@router.post("/context/{user_id}")
async def update_ai_context(user_id: str, request: Request):
    """Update AI context/memory for a user (merge update)."""
    user = await require_auth(request)
    if user.user_id != user_id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    update_data = {"last_updated": now}
    for key in ("preferences", "skill_profile", "goals", "conversation_history"):
        if key in body:
            update_data[key] = body[key]

    await db.ai_context.update_one(
        {"user_id": user_id},
        {"$set": update_data},
        upsert=True,
    )
    return {"success": True, "updated_at": now}


@router.get("/insights")
async def get_ai_insights(request: Request):
    """Generate AI insights based on platform-wide activity."""
    user = await require_auth(request)
    uid = user.user_id
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Aggregate user activity for the week
    sessions_count = await db.practice_sessions.count_documents(
        {"user_id": uid, "created_at": {"$gte": week_ago.isoformat()}}
    )
    apps_count = await db.applications.count_documents({"user_id": uid, "applied_at": {"$gte": week_ago.isoformat()}})
    bookings_count = await db.calendar_bookings.count_documents(
        {"user_id": uid, "created_at": {"$gte": week_ago.isoformat()}}
    )

    insights = []

    if sessions_count > 0:
        insights.append(
            {
                "type": "activity",
                "title": "Weekly Practice Summary",
                "description": f"You completed {sessions_count} practice session{'s' if sessions_count > 1 else ''} this week.",
                "metric": sessions_count,
                "trend": "up" if sessions_count >= 3 else "steady",
                "icon": "chatbubbles",
                "color": "#3B82F6",
            }
        )

    if apps_count > 0:
        insights.append(
            {
                "type": "career",
                "title": "Application Activity",
                "description": f"You applied to {apps_count} position{'s' if apps_count > 1 else ''} this week.",
                "metric": apps_count,
                "trend": "up",
                "icon": "briefcase",
                "color": "#10B981",
            }
        )

    if bookings_count > 0:
        insights.append(
            {
                "type": "meetings",
                "title": "Meeting Activity",
                "description": f"{bookings_count} meeting{'s' if bookings_count > 1 else ''} scheduled this week.",
                "metric": bookings_count,
                "trend": "up",
                "icon": "calendar",
                "color": "#8B5CF6",
            }
        )

    # Always include a tip
    insights.append(
        {
            "type": "tip",
            "title": "AI Tip of the Day",
            "description": "Consistent daily practice of 15 minutes improves interview performance by 40% on average.",
            "icon": "bulb",
            "color": "#F59E0B",
        }
    )

    return {"insights": insights, "period": "weekly", "generated_at": now.isoformat()}


@router.post("/track-engagement")
async def track_engagement(request: Request):
    """Track a user engagement event."""
    user = await require_auth(request)
    body = await request.json()

    event = {
        "event_id": f"eng_{uuid.uuid4().hex[:10]}",
        "user_id": user.user_id,
        "event_type": body.get("event_type", "page_view"),
        "page": body.get("page", ""),
        "duration_seconds": body.get("duration_seconds", 0),
        "metadata": body.get("metadata", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ai_engagement_events.insert_one(event)
    event.pop("_id", None)

    # Update engagement score
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    week_events = await db.ai_engagement_events.count_documents(
        {
            "user_id": user.user_id,
            "created_at": {"$gte": week_ago},
        }
    )

    score = min(100, week_events * 5)
    await db.ai_engagement.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "score": score,
                "weekly_events": week_events,
                "last_event": event["created_at"],
                "updated_at": event["created_at"],
            }
        },
        upsert=True,
    )

    return {"success": True, "event_id": event["event_id"], "engagement_score": score}


@router.get("/engagement-score")
async def get_engagement_score(request: Request):
    """Get user's engagement score and activity breakdown."""
    user = await require_auth(request)
    uid = user.user_id

    eng = await db.ai_engagement.find_one({"user_id": uid}, {"_id": 0})
    if not eng:
        eng = {"user_id": uid, "score": 0, "weekly_events": 0}

    # Get activity breakdown for the week
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pipeline = [
        {"$match": {"user_id": uid, "created_at": {"$gte": week_ago}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
    ]
    breakdown = await db.ai_engagement_events.aggregate(pipeline).to_list(20)

    return {
        "score": eng.get("score", 0),
        "weekly_events": eng.get("weekly_events", 0),
        "last_event": eng.get("last_event"),
        "breakdown": {b["_id"]: b["count"] for b in breakdown},
        "level": "Beginner" if eng.get("score", 0) < 30 else "Active" if eng.get("score", 0) < 70 else "Power User",
    }


@router.post("/chat")
async def ai_chat(request: Request):
    """AI chat endpoint — sends a message to Nova AI assistant and returns a response."""
    user = await require_auth(request)
    body = await request.json()
    message = body.get("message", "").strip()
    session_id = body.get("session_id", f"chat_{uuid.uuid4().hex[:8]}")

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    if not EMERGENT_KEY:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session_id,
            system_message="You are Nova, an expert AI coaching assistant for RealAICoach. You help users with career development, interview prep, skill building, job searching, and professional growth. Be helpful, encouraging, and provide actionable advice. Keep responses concise and focused.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=message))

        # Store in chat history
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        await db.ai_chat_history.insert_one({
            "msg_id": msg_id,
            "user_id": user.user_id,
            "session_id": session_id,
            "user_message": message,
            "assistant_response": response,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Auto-generate session title from first message
        existing_title = await db.ai_chat_sessions.find_one({"session_id": session_id, "user_id": user.user_id})
        if not existing_title:
            title = message[:60].strip()
            if len(message) > 60:
                title = title.rsplit(' ', 1)[0] + '...'
            await db.ai_chat_sessions.insert_one({
                "session_id": session_id,
                "user_id": user.user_id,
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        return {
            "msg_id": msg_id,
            "session_id": session_id,
            "response": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"AI chat failed: {e}")
        raise HTTPException(status_code=500, detail="AI chat service error")


@router.get("/chat/sessions")
async def get_chat_sessions(request: Request):
    """Get user's chat session history."""
    user = await require_auth(request)
    pipeline = [
        {"$match": {"user_id": user.user_id}},
        {"$group": {
            "_id": "$session_id",
            "last_message": {"$last": "$user_message"},
            "last_response": {"$last": "$assistant_response"},
            "message_count": {"$sum": 1},
            "last_at": {"$max": "$created_at"},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": 20},
    ]
    sessions = await db.ai_chat_history.aggregate(pipeline).to_list(20)

    # Fetch titles and summaries for each session
    session_ids = [s["_id"] for s in sessions]
    titles_cursor = db.ai_chat_sessions.find({"session_id": {"$in": session_ids}}, {"_id": 0, "session_id": 1, "title": 1, "summary": 1, "tags": 1})
    meta_map = {}
    async for t in titles_cursor:
        meta_map[t["session_id"]] = t

    return {"sessions": [{
        "session_id": s["_id"],
        "title": meta_map.get(s["_id"], {}).get("title", s["last_message"][:50]),
        "summary": meta_map.get(s["_id"], {}).get("summary"),
        "tags": meta_map.get(s["_id"], {}).get("tags", []),
        "last_message": s["last_message"],
        "message_count": s["message_count"],
        "last_at": s["last_at"],
    } for s in sessions]}


@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, request: Request):
    """Get messages for a specific chat session."""
    user = await require_auth(request)
    messages = await db.ai_chat_history.find(
        {"user_id": user.user_id, "session_id": session_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    return {"messages": messages, "session_id": session_id}


@router.post("/chat/sessions/summarize")
async def summarize_sessions(request: Request):
    """Auto-summarize older chat sessions into digest cards."""
    user = await require_auth(request)
    uid = user.user_id

    # Get all sessions sorted by recency
    pipeline = [
        {"$match": {"user_id": uid}},
        {"$group": {
            "_id": "$session_id",
            "message_count": {"$sum": 1},
            "last_at": {"$max": "$created_at"},
        }},
        {"$sort": {"last_at": -1}},
    ]
    sessions = await db.ai_chat_history.aggregate(pipeline).to_list(100)

    if len(sessions) < 5:
        return {"summarized": 0, "message": "Not enough sessions to summarize yet"}

    # Summarize sessions older than the 3 most recent (keep recent ones unsummarized)
    older_sessions = sessions[3:]
    already_summarized = set()
    existing = db.ai_chat_sessions.find(
        {"user_id": uid, "summary": {"$exists": True}},
        {"_id": 0, "session_id": 1}
    )
    async for doc in existing:
        already_summarized.add(doc["session_id"])

    to_summarize = [s for s in older_sessions if s["_id"] not in already_summarized]
    if not to_summarize:
        return {"summarized": 0, "message": "All sessions already summarized"}

    from emergentintegrations.llm.chat import LlmChat, UserMessage
    summarized_count = 0

    for session in to_summarize[:10]:  # Batch limit
        sid = session["_id"]
        msgs = await db.ai_chat_history.find(
            {"user_id": uid, "session_id": sid},
            {"_id": 0, "user_message": 1, "assistant_response": 1}
        ).sort("created_at", 1).to_list(50)

        if not msgs:
            continue

        # Build conversation text for summarization
        convo_text = "\n".join([
            f"User: {m['user_message']}\nAssistant: {m['assistant_response'][:200]}"
            for m in msgs[:15]  # Cap at 15 exchanges for token efficiency
        ])

        try:
            summary_chat = LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"summarize_{sid}",
                system_message="Summarize this coaching conversation in 2-3 concise sentences. Focus on the main topic discussed, key advice given, and any action items. Be direct and informative."
            ).with_model("openai", "gpt-4o-mini")
            summary_resp = await summary_chat.send_message(UserMessage(text=convo_text))
            summary_text = summary_resp

            tags_chat = LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"tags_{sid}",
                system_message="Extract 1-3 topic tags from this conversation summary. Return ONLY comma-separated tags, nothing else. Examples: leadership, career change, interview prep, resume, salary negotiation"
            ).with_model("openai", "gpt-4o-mini")
            tags_resp = await tags_chat.send_message(UserMessage(text=summary_text))
            tags = [t.strip().lower() for t in tags_resp.split(",") if t.strip()][:3]

            await db.ai_chat_sessions.update_one(
                {"session_id": sid, "user_id": uid},
                {"$set": {
                    "summary": summary_text,
                    "tags": tags,
                    "summarized_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True
            )
            summarized_count += 1
        except Exception as e:
            logger.warning(f"Failed to summarize session {sid}: {e}")
            continue

    return {"summarized": summarized_count, "total_sessions": len(sessions)}


@router.get("/chat/sessions/summaries")
async def get_session_summaries(request: Request):
    """Get all summarized sessions as digest cards."""
    user = await require_auth(request)
    cursor = db.ai_chat_sessions.find(
        {"user_id": user.user_id, "summary": {"$exists": True}},
        {"_id": 0, "session_id": 1, "title": 1, "summary": 1, "tags": 1, "summarized_at": 1, "created_at": 1}
    ).sort("created_at", -1)
    summaries = await cursor.to_list(50)
    return {"summaries": summaries, "count": len(summaries)}
