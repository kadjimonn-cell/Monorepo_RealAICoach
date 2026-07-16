"""AI Life Coach Hub — Multi-topic AI assistant for solving daily problems.

Supports: career, finance, wellness, productivity, relationships, education, legal, tech
Each conversation has persistent memory and generates actionable plans.

API:
- GET  /api/ai-coach/topics          — Available coaching topics
- GET  /api/ai-coach/conversations   — User's conversations
- POST /api/ai-coach/conversations   — Start new conversation
- GET  /api/ai-coach/conversations/{id}/messages — Get messages
- POST /api/ai-coach/conversations/{id}/messages — Send message + get AI reply
- POST /api/ai-coach/conversations/{id}/action-plan — Generate action plan
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import uuid
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate, ai_generate_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-coach")

TOPICS = [
    {
        "id": "career",
        "name": "Career & Jobs",
        "icon": "briefcase",
        "color": "#3B82F6",
        "desc": "Job search, interviews, career transitions, workplace issues",
        "system": "You are a world-class Career Coach. Help with job searching, interview prep, salary negotiation, career transitions, workplace conflicts, resume optimization, and professional development. Give specific, actionable advice.",
    },
    {
        "id": "finance",
        "name": "Finance & Money",
        "icon": "cash",
        "color": "#10B981",
        "desc": "Budgeting, saving, investing, debt management, financial planning",
        "system": "You are an expert Financial Advisor. Help with budgeting, saving strategies, debt repayment plans, investment basics, retirement planning, and financial literacy. Always remind users to consult a licensed advisor for specific investment decisions. Give practical, step-by-step guidance.",
    },
    {
        "id": "wellness",
        "name": "Health & Wellness",
        "icon": "heart",
        "color": "#EF4444",
        "desc": "Mental health, fitness, nutrition, stress, sleep, mindfulness",
        "system": "You are a compassionate Wellness Coach. Help with stress management, mindfulness, sleep hygiene, fitness routines, nutrition basics, mental health awareness, and work-life balance. Always recommend professional medical help for serious concerns. Be empathetic and supportive.",
    },
    {
        "id": "productivity",
        "name": "Productivity",
        "icon": "rocket",
        "color": "#F59E0B",
        "desc": "Time management, habits, focus, organization, goal setting",
        "system": "You are a Productivity Expert. Help with time management techniques, habit building, focus strategies, task prioritization, project planning, and overcoming procrastination. Give specific frameworks and actionable tips.",
    },
    {
        "id": "relationships",
        "name": "Relationships",
        "icon": "people",
        "color": "#EC4899",
        "desc": "Communication, conflict resolution, family, friendship, networking",
        "system": "You are a Relationship Coach. Help with communication skills, conflict resolution, building healthy relationships, networking, family dynamics, and social skills. Be empathetic, non-judgmental, and give balanced perspectives.",
    },
    {
        "id": "education",
        "name": "Learning & Education",
        "icon": "school",
        "color": "#8B5CF6",
        "desc": "Study skills, course selection, certifications, skill development",
        "system": "You are an Education Advisor. Help with study strategies, learning techniques, course/certification recommendations, skill development roadmaps, academic planning, and lifelong learning paths. Give specific resources and structured plans.",
    },
    {
        "id": "legal",
        "name": "Legal Guidance",
        "icon": "shield-checkmark",
        "color": "#6366F1",
        "desc": "Rights, contracts, disputes, compliance basics",
        "system": "You are a Legal Information Assistant. Help users understand their basic rights, contract terms, dispute resolution options, and compliance basics. ALWAYS emphasize you provide general information only and recommend consulting a licensed attorney for specific legal matters.",
    },
    {
        "id": "tech",
        "name": "Tech & Digital",
        "icon": "code-slash",
        "color": "#06B6D4",
        "desc": "Troubleshooting, digital literacy, online safety, tool recommendations",
        "system": "You are a Tech Support Expert. Help with software troubleshooting, digital literacy, online safety, privacy practices, tool recommendations, and technology learning paths. Give clear, step-by-step instructions.",
    },
]

TOPIC_MAP = {t["id"]: t for t in TOPICS}


class NewConversation(BaseModel):
    topic_id: str
    title: Optional[str] = None


class SendMessage(BaseModel):
    content: str


@router.get("/topics")
async def get_topics(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return {"topics": [{k: v for k, v in t.items() if k != "system"} for t in TOPICS]}


@router.get("/conversations")
async def get_conversations(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    convos = await db.coach_conversations.find({"user_id": user.user_id}, {"_id": 0}).sort("updated_at", -1).to_list(50)
    return {"conversations": convos}


@router.post("/conversations")
async def create_conversation(request: Request, body: NewConversation):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    topic = TOPIC_MAP.get(body.topic_id)
    if not topic:
        raise HTTPException(400, "Invalid topic")
    now = datetime.now(timezone.utc).isoformat()
    convo = {
        "conversation_id": f"coach_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "topic_id": body.topic_id,
        "topic_name": topic["name"],
        "topic_icon": topic["icon"],
        "topic_color": topic["color"],
        "title": body.title or f"New {topic['name']} Session",
        "message_count": 0,
        "has_action_plan": False,
        "created_at": now,
        "updated_at": now,
    }
    await db.coach_conversations.insert_one(convo)
    return {k: v for k, v in convo.items() if k != "_id"}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(request: Request, conversation_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    convo = await db.coach_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not convo:
        raise HTTPException(404, "Conversation not found")
    msgs = (
        await db.coach_messages.find({"conversation_id": conversation_id}, {"_id": 0})
        .sort("created_at", 1)
        .to_list(200)
    )
    plan = await db.coach_action_plans.find_one({"conversation_id": conversation_id}, {"_id": 0})
    return {"conversation": convo, "messages": msgs, "action_plan": plan}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(request: Request, conversation_id: str, body: SendMessage):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    convo = await db.coach_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not convo:
        raise HTTPException(404, "Conversation not found")

    topic = TOPIC_MAP.get(convo["topic_id"], TOPICS[0])
    now = datetime.now(timezone.utc).isoformat()

    # Save user message
    user_msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "conversation_id": conversation_id,
        "role": "user",
        "content": body.content,
        "created_at": now,
    }
    await db.coach_messages.insert_one(user_msg)

    # Build context from recent messages
    recent = (
        await db.coach_messages.find({"conversation_id": conversation_id}, {"_id": 0, "role": 1, "content": 1})
        .sort("created_at", -1)
        .limit(10)
        .to_list(10)
    )
    recent.reverse()
    context = "\n".join([f"{'User' if m['role'] == 'user' else 'Coach'}: {m['content'][:300]}" for m in recent])

    # Generate AI response
    system_msg = (
        topic["system"]
        + f"\n\nUser name: {getattr(user, 'name', 'User')}. Be warm, specific, and actionable. Reference their previous messages for continuity."
    )
    prompt = f"Conversation history:\n{context}\n\nUser's latest message: {body.content}\n\nProvide a helpful, specific response:"

    try:
        ai_text = await ai_generate(system_msg, prompt, f"coach-{conversation_id}")
    except Exception as e:
        logger.error(f"AI Coach error: {e}")
        ai_text = "I understand your concern. Let me help you think through this step by step. Could you tell me more about your specific situation so I can give you the most relevant advice?"

    ai_msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "conversation_id": conversation_id,
        "role": "assistant",
        "content": ai_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.coach_messages.insert_one(ai_msg)

    # Update conversation
    await db.coach_conversations.update_one(
        {"conversation_id": conversation_id},
        {
            "$set": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "title": body.content[:60] if convo.get("message_count", 0) == 0 else convo["title"],
            },
            "$inc": {"message_count": 2},
        },
    )

    return {
        "user_message": {k: v for k, v in user_msg.items() if k != "_id"},
        "ai_message": {k: v for k, v in ai_msg.items() if k != "_id"},
    }


@router.post("/conversations/{conversation_id}/action-plan")
async def generate_action_plan(request: Request, conversation_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    convo = await db.coach_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not convo:
        raise HTTPException(404, "Conversation not found")

    msgs = (
        await db.coach_messages.find({"conversation_id": conversation_id}, {"_id": 0, "role": 1, "content": 1})
        .sort("created_at", 1)
        .to_list(30)
    )
    context = "\n".join([f"{'User' if m['role'] == 'user' else 'Coach'}: {m['content'][:200]}" for m in msgs])

    system_msg = """You are an expert Action Plan Generator. Based on the coaching conversation, create a structured, actionable plan.
Return ONLY valid JSON:
{
  "title": "Plan title",
  "summary": "Brief summary of the goal",
  "milestones": [
    {"id": 1, "title": "Milestone title", "description": "What to do", "timeframe": "1 week", "priority": "high"},
    ...
  ],
  "quick_wins": ["Quick win 1", "Quick win 2"],
  "resources": ["Resource or tip 1", "Resource 2"]
}"""
    prompt = f"Conversation:\n{context}\n\nGenerate a detailed action plan with 4-6 milestones:"

    try:
        plan_data = await ai_generate_json(system_msg, prompt, f"plan-{conversation_id}")
    except Exception as e:
        logger.error(f"Action plan generation error: {e}")
        plan_data = {
            "title": "Your Action Plan",
            "summary": "Based on our conversation",
            "milestones": [
                {
                    "id": 1,
                    "title": "Review discussion points",
                    "description": "Go through the key topics we discussed",
                    "timeframe": "Today",
                    "priority": "high",
                }
            ],
            "quick_wins": ["Start with the first step today"],
            "resources": ["Review our conversation for detailed guidance"],
        }

    now = datetime.now(timezone.utc).isoformat()
    plan = {
        "plan_id": f"plan_{uuid.uuid4().hex[:12]}",
        "conversation_id": conversation_id,
        "user_id": user.user_id,
        **plan_data,
        "created_at": now,
    }
    await db.coach_action_plans.update_one(
        {"conversation_id": conversation_id},
        {"$set": {k: v for k, v in plan.items()}},
        upsert=True,
    )
    await db.coach_conversations.update_one({"conversation_id": conversation_id}, {"$set": {"has_action_plan": True}})
    return plan
