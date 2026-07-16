"""LifeGame RPG routes: character creation, quests, coaching, mood tracking, leaderboard."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List
import re
import json
from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, EMERGENT_LLM_KEY, logger


def _resp_text(response):
    return response.text if hasattr(response, "text") else str(response)


router = APIRouter()


class LifeGameCharacterCreate(BaseModel):
    user_id: str
    name: str
    archetype: str = "Explorer"
    focus_areas: List[str] = ["productivity", "health", "finance"]


class LifeGameQuestRequest(BaseModel):
    user_id: str
    energy_level: str = "medium"
    available_time: int = 60
    mood: str = "neutral"


class LifeGameCompleteQuest(BaseModel):
    user_id: str
    quest_id: str
    difficulty_felt: str = "just_right"
    notes: str = ""


class LifeGameCoachRequest(BaseModel):
    user_id: str
    message: str
    context: str = "general"


class LifeGameMoodCheck(BaseModel):
    user_id: str
    mood: int
    energy: int
    stress: int
    sleep_hours: float = 7.0
    notes: str = ""


ARCHETYPES = {
    "Explorer": {"emoji": "compass", "bonus": "creativity", "desc": "Curious mind, loves discovering new things"},
    "Warrior": {"emoji": "shield", "bonus": "discipline", "desc": "Strong-willed, thrives on challenges"},
    "Scholar": {"emoji": "book", "bonus": "learning", "desc": "Knowledge seeker, loves mastering skills"},
    "Healer": {"emoji": "heart", "bonus": "wellness", "desc": "Nurturing spirit, prioritizes balance"},
    "Builder": {"emoji": "construct", "bonus": "productivity", "desc": "Creates and builds, goal-oriented"},
}

SKILL_TREES = {
    "productivity": {"icon": "flash", "name": "Productivity", "color": "#3B82F6"},
    "health": {"icon": "heart", "name": "Health & Wellness", "color": "#EF4444"},
    "finance": {"icon": "cash", "name": "Financial Growth", "color": "#10B981"},
    "learning": {"icon": "bulb", "name": "Knowledge", "color": "#8B5CF6"},
    "social": {"icon": "people", "name": "Social & EQ", "color": "#F59E0B"},
    "creativity": {"icon": "color-palette", "name": "Creativity", "color": "#EC4899"},
}


@router.post("/lifegame/create-character")
async def lifegame_create_character(request: LifeGameCharacterCreate):
    existing = await db.lifegame_characters.find_one({"user_id": request.user_id})
    archetype_info = ARCHETYPES.get(request.archetype, ARCHETYPES["Explorer"])
    skills = {area: (10 if area in request.focus_areas else 5) for area in SKILL_TREES}

    character = {
        "user_id": request.user_id,
        "name": request.name,
        "archetype": request.archetype,
        "level": 1,
        "xp": 0,
        "xp_to_next": 100,
        "total_xp": 0,
        "skills": skills,
        "streak": 0,
        "longest_streak": 0,
        "quests_completed": 0,
        "badges": ["New Adventurer"],
        "title": "Novice",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        await db.lifegame_characters.update_one(
            {"user_id": request.user_id},
            {"$set": {**character, "created_at": existing.get("created_at", character["created_at"])}},
        )
    else:
        doc = {**character}
        await db.lifegame_characters.insert_one(doc)

    return {
        "success": True,
        "character": {**character, "archetype_info": archetype_info},
        "message": f"Welcome, {request.name} the {request.archetype}! Your adventure begins now.",
    }


@router.get("/lifegame/character/{user_id}")
async def lifegame_get_character(user_id: str):
    char = await db.lifegame_characters.find_one({"user_id": user_id}, {"_id": 0})
    if not char:
        return {
            "exists": False,
            "character": None,
            "message": "No character found. Create one to start your adventure!",
        }

    archetype_info = ARCHETYPES.get(char.get("archetype", "Explorer"), ARCHETYPES["Explorer"])
    titles = ["Novice", "Apprentice", "Journeyman", "Adept", "Expert", "Master", "Grandmaster", "Legend"]
    level = char.get("level", 1)
    title = titles[min(level // 5, len(titles) - 1)]

    return {
        "exists": True,
        "character": {**char, "archetype_info": archetype_info, "title": title},
        "skill_trees": SKILL_TREES,
    }


@router.post("/lifegame/daily-quests")
async def lifegame_daily_quests(request: LifeGameQuestRequest):
    char = await db.lifegame_characters.find_one({"user_id": request.user_id}, {"_id": 0})
    level = char.get("level", 1) if char else 1
    archetype = char.get("archetype", "Explorer") if char else "Explorer"
    skills = char.get("skills", {}) if char else {}

    weakest_skills = sorted(skills.items(), key=lambda x: x[1])[:2] if skills else []
    weak_areas = ", ".join([s[0] for s in weakest_skills]) if weakest_skills else "general growth"

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"lifegame-quests-{request.user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            system_message="You are a helpful AI assistant.",
        )

        prompt = f"""You are the Quest Master in LifeGame, an RPG life-coaching game. Generate personalized daily quests.

Player Profile:
- Level: {level}, Archetype: {archetype}
- Energy: {request.energy_level}, Mood: {request.mood}
- Available Time: {request.available_time} minutes
- Weakest Skills: {weak_areas}

Generate 5 quests in JSON format. Mix quest types: main quest (1), side quests (2), daily habits (2).
Adapt difficulty to energy/mood. Low energy = lighter tasks. High energy = challenging tasks.

Return ONLY this JSON:
{{
    "quests": [
        {{
            "id": "quest_1",
            "title": "Quest title",
            "description": "What to do and why",
            "type": "main_quest",
            "skill": "productivity",
            "xp_reward": 50,
            "difficulty": "medium",
            "time_estimate": "15 min",
            "emoji": "target"
        }}
    ],
    "daily_message": "Motivational message for the day",
    "burnout_risk": "low",
    "recommended_focus": "Which skill to prioritize today"
}}"""

        response = await chat.send_message(UserMessage(text=prompt))
        try:
            json_match = re.search(r"\{[\s\S]*\}", _resp_text(response))
            if json_match:
                result = json.loads(json_match.group())
                if "quests" in result:
                    return result
        except Exception:
            pass
    except Exception as e:
        logger.error(f"LifeGame quest generation error: {e}")

    energy_mult = {"low": 0.7, "medium": 1.0, "high": 1.3}.get(request.energy_level, 1.0)
    base_xp = int(30 * energy_mult)

    return {
        "quests": [
            {
                "id": "quest_main",
                "title": "Deep Work Session",
                "description": "Focus on your most important task for 25 minutes without distractions",
                "type": "main_quest",
                "skill": "productivity",
                "xp_reward": base_xp + 30,
                "difficulty": "medium",
                "time_estimate": "25 min",
                "emoji": "target",
            },
            {
                "id": "quest_side1",
                "title": "Knowledge Quest",
                "description": "Read an article or watch a tutorial about something new",
                "type": "side_quest",
                "skill": "learning",
                "xp_reward": base_xp,
                "difficulty": "easy",
                "time_estimate": "15 min",
                "emoji": "book",
            },
            {
                "id": "quest_side2",
                "title": "Body Boost",
                "description": "Take a 10-minute walk or do a quick workout",
                "type": "side_quest",
                "skill": "health",
                "xp_reward": base_xp,
                "difficulty": "easy",
                "time_estimate": "10 min",
                "emoji": "barbell",
            },
            {
                "id": "quest_habit1",
                "title": "Gratitude Log",
                "description": "Write 3 things you're grateful for today",
                "type": "daily_habit",
                "skill": "social",
                "xp_reward": base_xp - 10,
                "difficulty": "easy",
                "time_estimate": "5 min",
                "emoji": "heart",
            },
            {
                "id": "quest_habit2",
                "title": "Budget Check",
                "description": "Review today's spending and track expenses",
                "type": "daily_habit",
                "skill": "finance",
                "xp_reward": base_xp - 10,
                "difficulty": "easy",
                "time_estimate": "5 min",
                "emoji": "cash",
            },
        ],
        "daily_message": "Every quest completed is a step toward the life you want. Let's make today count!",
        "burnout_risk": "low" if request.mood in ["great", "good"] else "medium",
        "recommended_focus": weak_areas if weakest_skills else "productivity",
    }


@router.post("/lifegame/complete-quest")
async def lifegame_complete_quest(request: LifeGameCompleteQuest):
    char = await db.lifegame_characters.find_one({"user_id": request.user_id})
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    difficulty_bonus = {"too_easy": 0.8, "just_right": 1.0, "challenging": 1.2, "too_hard": 1.5}
    multiplier = difficulty_bonus.get(request.difficulty_felt, 1.0)
    earned_xp = int(40 * multiplier)

    new_xp = char.get("xp", 0) + earned_xp
    new_total = char.get("total_xp", 0) + earned_xp
    xp_to_next = char.get("xp_to_next", 100)
    new_level = char.get("level", 1)
    leveled_up = False
    new_badges = list(char.get("badges", []))
    quests_done = char.get("quests_completed", 0) + 1

    while new_xp >= xp_to_next:
        new_xp -= xp_to_next
        new_level += 1
        xp_to_next = int(xp_to_next * 1.3)
        leveled_up = True

    if quests_done == 1 and "First Quest" not in new_badges:
        new_badges.append("First Quest")
    if quests_done == 10 and "Quest Warrior" not in new_badges:
        new_badges.append("Quest Warrior")
    if quests_done == 50 and "Quest Master" not in new_badges:
        new_badges.append("Quest Master")
    if new_level >= 5 and "Rising Star" not in new_badges:
        new_badges.append("Rising Star")
    if new_level >= 10 and "Diamond Player" not in new_badges:
        new_badges.append("Diamond Player")

    await db.lifegame_characters.update_one(
        {"user_id": request.user_id},
        {
            "$set": {
                "xp": new_xp,
                "total_xp": new_total,
                "level": new_level,
                "xp_to_next": xp_to_next,
                "quests_completed": quests_done,
                "badges": new_badges,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    return {
        "success": True,
        "xp_earned": earned_xp,
        "total_xp": new_total,
        "new_xp": new_xp,
        "xp_to_next": xp_to_next,
        "level": new_level,
        "leveled_up": leveled_up,
        "quests_completed": quests_done,
        "badges": new_badges,
        "message": f"Level Up! You're now Level {new_level}!" if leveled_up else f"+{earned_xp} XP earned! Keep going!",
    }


@router.post("/lifegame/ai-coach")
async def lifegame_ai_coach(request: LifeGameCoachRequest):
    char = await db.lifegame_characters.find_one({"user_id": request.user_id}, {"_id": 0})
    level = char.get("level", 1) if char else 1
    archetype = char.get("archetype", "Explorer") if char else "Explorer"

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"lifegame-coach-{request.user_id}",
            system_message="You are a helpful AI assistant.",
        )

        system_context = f"""You are the AI Coach in LifeGame, a life-RPG app. You combine:
- Therapist wisdom (empathetic, validating)
- Productivity strategist (actionable, structured)
- Fitness coach (motivating, goal-oriented)
- Financial planner (practical, forward-thinking)
- Life mentor (inspiring, experience-based)

Player is Level {level}, Archetype: {archetype}. Context: {request.context}.
Use RPG metaphors naturally. Be warm, specific, and actionable. Keep responses concise (3-4 paragraphs max).
If detecting burnout signs, prioritize rest and recovery advice."""

        prompt = f"{system_context}\n\nPlayer message: {request.message}"
        response = await chat.send_message(UserMessage(text=prompt))

        return {
            "response": _resp_text(response),
            "coach_type": request.context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"LifeGame coach error: {e}")
        fallback_responses = {
            "burnout": "I can see you're running low on HP! Every great adventurer needs rest to recharge. Take a break, hydrate, and remember: recovery IS progress.",
            "motivation": "Even the greatest heroes started at Level 1. Every small quest you complete adds XP to your life. You're further ahead than you think.",
            "planning": "Let's map out your quest log! Start with your Main Quest (most important goal), then add 2-3 Side Quests.",
            "reflection": "Time for a save point! Reflect on your recent wins. What skill did you level up this week?",
            "general": "Welcome back, adventurer! Ready to earn some XP today? Consistency beats intensity.",
        }
        return {
            "response": fallback_responses.get(request.context, fallback_responses["general"]),
            "coach_type": request.context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/lifegame/mood-check")
async def lifegame_mood_check(request: LifeGameMoodCheck):
    mood_entry = {
        "user_id": request.user_id,
        "mood": request.mood,
        "energy": request.energy,
        "stress": request.stress,
        "sleep_hours": request.sleep_hours,
        "notes": request.notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.lifegame_moods.insert_one(mood_entry)

    recommendations = []
    quest_intensity = "medium"

    if request.stress >= 7:
        recommendations.append(
            {
                "type": "wellness",
                "emoji": "leaf",
                "text": "High stress detected. Try a 5-min breathing exercise before your quests.",
            }
        )
        quest_intensity = "low"
    if request.energy <= 3:
        recommendations.append(
            {"type": "rest", "emoji": "moon", "text": "Low energy — focus on easy quests today. Rest is a power-up!"}
        )
        quest_intensity = "low"
    if request.sleep_hours < 6:
        recommendations.append(
            {
                "type": "sleep",
                "emoji": "bed",
                "text": f"Only {request.sleep_hours}h sleep. Prioritize an early bedtime tonight.",
            }
        )
    if request.mood >= 8:
        recommendations.append(
            {"type": "momentum", "emoji": "rocket", "text": "Great mood! Perfect time to tackle your hardest quest."}
        )
        quest_intensity = "high"
    if request.mood <= 3:
        recommendations.append(
            {
                "type": "comfort",
                "emoji": "heart",
                "text": "Tough day? Start with a small win to build momentum. You've got this.",
            }
        )
        quest_intensity = "low"
    if request.energy >= 8 and request.stress <= 3:
        recommendations.append(
            {
                "type": "challenge",
                "emoji": "flash",
                "text": "Peak performance mode! Take on a challenging quest for bonus XP.",
            }
        )
        quest_intensity = "high"

    if not recommendations:
        recommendations.append(
            {
                "type": "balanced",
                "emoji": "sparkles",
                "text": "You're in a balanced state. Great foundation for steady progress!",
            }
        )

    burnout_risk = (
        "high" if (request.stress >= 7 and request.energy <= 4) else "medium" if request.stress >= 5 else "low"
    )

    return {
        "logged": True,
        "recommendations": recommendations,
        "quest_intensity": quest_intensity,
        "burnout_risk": burnout_risk,
        "wellness_score": round((request.mood + request.energy + (10 - request.stress)) / 3, 1),
        "message": "Mood logged! Your quests have been adapted to your current state.",
    }


@router.get("/lifegame/leaderboard")
async def lifegame_leaderboard():
    leaders = (
        await db.lifegame_characters.find(
            {}, {"_id": 0, "user_id": 1, "name": 1, "archetype": 1, "level": 1, "total_xp": 1, "quests_completed": 1}
        )
        .sort("total_xp", -1)
        .limit(20)
        .to_list(20)
    )

    for i, leader in enumerate(leaders):
        leader["rank"] = i + 1
        arch = ARCHETYPES.get(leader.get("archetype", "Explorer"), ARCHETYPES["Explorer"])
        leader["emoji"] = arch["emoji"]

    return {"leaderboard": leaders, "total_players": await db.lifegame_characters.count_documents({})}
