"""Analytics routes: Dashboard, Weekly Insights."""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
import uuid
import json
from .db import db, EMERGENT_LLM_KEY, logger
from emergentintegrations.llm.chat import LlmChat, UserMessage

router = APIRouter()

FEATURE_NAMES = {
    "medimate": "MediMate",
    "pennypilot": "PennyPilot",
    "assistant": "TaskTool",
    "smartbuy": "SmartBuy",
    "fitness": "Fitness",
    "travelpal": "TravelPal",
    "grammarly": "AI Writer",
    "jasper": "AI Copywriter",
    "picsart": "AI Photo",
    "bemyai": "AI Vision",
    "zapier": "Automations",
    "chatgpt": "AI Chatbot",
    "cognitive": "AI Cognitive",
    "enterprise": "AI Enterprise",
    "privatesearch": "Private Search",
    "speech": "AI Speech",
    "ai-search": "AI Search",
}


@router.get("/analytics/dashboard/{user_id}")
async def get_analytics_dashboard(user_id: str):
    pipeline_features = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$feature", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    feature_usage = []
    async for doc in db.tool_usage.aggregate(pipeline_features):
        feature_usage.append(
            {"feature": doc["_id"], "name": FEATURE_NAMES.get(doc["_id"], doc["_id"]), "count": doc["count"]}
        )

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pipeline_daily = [
        {"$match": {"user_id": user_id, "timestamp": {"$gte": seven_days_ago}}},
        {"$addFields": {"day": {"$substr": ["$timestamp", 0, 10]}}},
        {"$group": {"_id": "$day", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    daily_usage = []
    async for doc in db.tool_usage.aggregate(pipeline_daily):
        daily_usage.append({"date": doc["_id"], "count": doc["count"]})

    total_interactions = await db.tool_usage.count_documents({"user_id": user_id})
    total_conversations = await db.conversations.count_documents({"user_id": user_id})

    recent = await db.tool_usage.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)

    return {
        "feature_usage": feature_usage,
        "daily_usage": daily_usage,
        "total_interactions": total_interactions,
        "total_conversations": total_conversations,
        "total_features_used": len(feature_usage),
        "recent_activity": recent,
    }


@router.post("/insights/weekly/{user_id}")
async def generate_weekly_insights(user_id: str):
    try:
        progress = await db.progress.find_one({"user_id": user_id}, {"_id": 0})
        conversations = await db.conversations.find({"user_id": user_id}).sort("created_at", -1).limit(10).to_list(10)
        await db.ai_searches.find({"user_id": user_id}).sort("created_at", -1).limit(5).to_list(5)

        skills = progress.get("skills", {}) if progress else {}
        xp = progress.get("xp", 0) if progress else 0
        level = progress.get("level", 1) if progress else 1
        streak = progress.get("current_streak", 0) if progress else 0

        prompt = f"""Generate a personalized weekly insights digest for a RealAICoach user:
User Stats: Level {level}, XP {xp}, Streak {streak} days, Skills: {json.dumps(skills)}, Conversations: {len(conversations)}.
Create: 1) Greeting + progress summary 2) Top 3 highlights 3) Areas to improve 4) Motivational message 5) Feature recommendation.
Keep concise and actionable."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"insights-{uuid.uuid4().hex[:8]}",
            system_message="You are RealAICoach's weekly insights generator.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))

        digest = {
            "digest_id": str(uuid.uuid4().hex[:12]),
            "user_id": user_id,
            "content": response.strip(),
            "stats": {"level": level, "xp": xp, "streak": streak, "conversations": len(conversations)},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.weekly_digests.insert_one({**digest})
        await db.notifications.insert_one(
            {
                "id": str(uuid.uuid4().hex[:12]),
                "user_id": user_id,
                "type": "weekly_digest",
                "title": "Your Weekly AI Insights",
                "message": "Your personalized weekly digest is ready!",
                "read": False,
                "data": {"digest_id": digest["digest_id"]},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {
            "digest_id": digest["digest_id"],
            "content": response.strip(),
            "stats": digest["stats"],
            "created_at": digest["created_at"],
        }
    except Exception as e:
        logger.error(f"Weekly insights error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate weekly insights")


@router.get("/insights/history/{user_id}")
async def get_insights_history(user_id: str, limit: int = 10):
    digests = (
        await db.weekly_digests.find({"user_id": user_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    return {"digests": digests}
