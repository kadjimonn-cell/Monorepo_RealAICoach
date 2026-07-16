"""Assistant and Translation routes."""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import db, EMERGENT_LLM_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

# ══════════ MODELS ══════════

# ============== AI LIFE ASSISTANT MODELS ==============


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: str = "medium"  # low, medium, high, urgent
    category: str = "general"  # work, personal, health, shopping, etc.
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None  # daily, weekly, monthly
    completed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskCreateRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: str = "medium"
    category: str = "general"
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None


class ScheduleEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: Optional[str] = None
    date: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    category: str = "general"
    reminders: List[int] = [30]  # minutes before


class ScheduleEventRequest(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    date: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    category: str = "general"


class ShoppingListItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    quantity: int = 1
    unit: Optional[str] = None
    category: str = "general"  # groceries, household, electronics, etc.
    purchased: bool = False
    store: Optional[str] = None


class ShoppingListRequest(BaseModel):
    user_id: str
    items: List[Dict[str, Any]]  # List of items to add


class DailyPlanRequest(BaseModel):
    user_id: str
    date: str
    goals: List[str] = []
    energy_level: str = "medium"  # low, medium, high
    available_hours: float = 8.0


class HabitTrackRequest(BaseModel):
    user_id: str
    habit_name: str
    completed: bool = True
    date: Optional[str] = None
    notes: Optional[str] = None


class LifeAssistantChatRequest(BaseModel):
    user_id: str
    message: str
    context: Optional[str] = None  # planning, reminders, shopping, general


# ============== UNIVERSAL TRANSLATION HUB MODELS ==============


class TranslateTextRequest(BaseModel):
    user_id: str
    text: str
    source_language: str = "auto"  # auto-detect or specify
    target_language: str
    context: Optional[str] = None  # formal, casual, technical, medical


class TranslateSpeechRequest(BaseModel):
    user_id: str
    audio_base64: str
    source_language: str = "auto"
    target_language: str
    output_format: str = "text"  # text or audio


class ConversationTranslateRequest(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    my_language: str
    their_language: str


# ══════════ ASSISTANT ROUTES ══════════


@router.post("/assistant/tasks/create")
async def create_task(request: TaskCreateRequest):
    """Create a new task"""
    try:
        task = Task(
            title=request.title,
            description=request.description,
            due_date=request.due_date,
            due_time=request.due_time,
            priority=request.priority,
            category=request.category,
            is_recurring=request.is_recurring,
            recurrence_pattern=request.recurrence_pattern,
        )

        task_dict = task.dict()
        task_dict["user_id"] = request.user_id

        await db.tasks.insert_one(task_dict)

        # Remove MongoDB _id from response
        task_dict.pop("_id", None)

        return {"message": "Task created successfully", "task": task_dict}

    except Exception as e:
        logger.error(f"Task creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assistant/tasks/{user_id}")
async def get_tasks(user_id: str, category: Optional[str] = None, completed: Optional[bool] = None):
    """Get all tasks for a user"""
    query = {"user_id": user_id}
    if category:
        query["category"] = category
    if completed is not None:
        query["completed"] = completed

    tasks = await db.tasks.find(query, {"_id": 0}).sort("due_date", 1).to_list(100)
    return {"tasks": tasks}


@router.put("/assistant/tasks/{task_id}/complete")
async def complete_task(task_id: str, user_id: str):
    """Mark a task as completed"""
    result = await db.tasks.update_one(
        {"id": task_id, "user_id": user_id}, {"$set": {"completed": True, "completed_at": datetime.utcnow()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task completed"}


@router.delete("/assistant/tasks/{task_id}")
async def delete_task(task_id: str, user_id: str):
    """Delete a task"""
    result = await db.tasks.delete_one({"id": task_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/assistant/schedule/event")
async def create_schedule_event(request: ScheduleEventRequest):
    """Create a calendar event"""
    try:
        event = ScheduleEvent(
            title=request.title,
            description=request.description,
            date=request.date,
            start_time=request.start_time,
            end_time=request.end_time,
            location=request.location,
            category=request.category,
        )

        event_dict = event.dict()
        event_dict["user_id"] = request.user_id

        await db.schedule_events.insert_one(event_dict)

        # Remove MongoDB _id from response
        event_dict.pop("_id", None)

        return {"message": "Event created successfully", "event": event_dict}

    except Exception as e:
        logger.error(f"Event creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assistant/schedule/{user_id}")
async def get_schedule(user_id: str, date: Optional[str] = None):
    """Get schedule/calendar events"""
    query = {"user_id": user_id}
    if date:
        query["date"] = date

    events = await db.schedule_events.find(query, {"_id": 0}).sort([("date", 1), ("start_time", 1)]).to_list(100)
    return {"events": events}


@router.post("/assistant/shopping-list/add")
async def add_shopping_items(request: ShoppingListRequest):
    """Add items to shopping list"""
    try:
        items_added = []
        for item in request.items:
            shopping_item = ShoppingListItem(
                name=item.get("name"),
                quantity=item.get("quantity", 1),
                unit=item.get("unit"),
                category=item.get("category", "general"),
                store=item.get("store"),
            )
            item_dict = shopping_item.dict()
            item_dict["user_id"] = request.user_id
            await db.shopping_list.insert_one(item_dict)
            items_added.append(item_dict)

        return {"message": f"Added {len(items_added)} items", "items": items_added}

    except Exception as e:
        logger.error(f"Shopping list update failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assistant/shopping-list/{user_id}")
async def get_shopping_list(user_id: str, purchased: Optional[bool] = None):
    """Get shopping list"""
    query = {"user_id": user_id}
    if purchased is not None:
        query["purchased"] = purchased

    items = await db.shopping_list.find(query, {"_id": 0}).to_list(100)

    # Group by category
    by_category = {}
    for item in items:
        cat = item.get("category", "general")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(item)

    return {"items": items, "by_category": by_category}


@router.put("/assistant/shopping-list/{item_id}/purchase")
async def mark_item_purchased(item_id: str, user_id: str):
    """Mark a shopping item as purchased"""
    result = await db.shopping_list.update_one({"id": item_id, "user_id": user_id}, {"$set": {"purchased": True}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item marked as purchased"}


@router.post("/assistant/habits/track")
async def track_habit(request: HabitTrackRequest):
    """Track a daily habit"""
    try:
        date = request.date or datetime.utcnow().strftime("%Y-%m-%d")

        await db.habits.update_one(
            {"user_id": request.user_id, "habit_name": request.habit_name, "date": date},
            {"$set": {"completed": request.completed, "notes": request.notes, "tracked_at": datetime.utcnow()}},
            upsert=True,
        )

        # Calculate streak
        habit_history = (
            await db.habits.find({"user_id": request.user_id, "habit_name": request.habit_name, "completed": True})
            .sort("date", -1)
            .to_list(100)
        )

        streak = 0
        for i, h in enumerate(habit_history):
            expected_date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            if h.get("date") == expected_date:
                streak += 1
            else:
                break

        return {"message": "Habit tracked", "current_streak": streak}

    except Exception as e:
        logger.error(f"Habit tracking failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assistant/habits/{user_id}")
async def get_habits(user_id: str, habit_name: Optional[str] = None):
    """Get habit tracking data"""
    query = {"user_id": user_id}
    if habit_name:
        query["habit_name"] = habit_name

    habits = await db.habits.find(query, {"_id": 0}).sort("date", -1).to_list(100)

    # Group by habit name
    by_habit = {}
    for h in habits:
        name = h.get("habit_name")
        if name not in by_habit:
            by_habit[name] = []
        by_habit[name].append(h)

    return {"habits": habits, "by_habit": by_habit}


@router.post("/assistant/daily-plan")
async def create_daily_plan(request: DailyPlanRequest):
    """Generate an AI-optimized daily plan"""
    try:
        # Get user's tasks and events
        tasks = await db.tasks.find({"user_id": request.user_id, "completed": False}).to_list(50)

        events = await db.schedule_events.find({"user_id": request.user_id, "date": request.date}).to_list(20)

        prompt = f"""Create an optimized daily plan.

Date: {request.date}
User's Goals for Today: {", ".join(request.goals) if request.goals else "No specific goals set"}
Energy Level: {request.energy_level}
Available Hours: {request.available_hours}

Existing Tasks (incomplete):
{json.dumps([{"title": t["title"], "priority": t.get("priority", "medium"), "due_date": t.get("due_date")} for t in tasks[:10]], indent=2)}

Scheduled Events:
{json.dumps([{"title": e["title"], "start": e.get("start_time"), "end": e.get("end_time")} for e in events], indent=2)}

Create an intelligent daily plan that:
1. Schedules high-priority tasks during peak energy times
2. Accounts for existing events
3. Includes breaks and buffer time
4. Suggests optimal task ordering
5. Provides time estimates

Return JSON:
{{
    "date": "{request.date}",
    "daily_theme": "Theme or focus for the day",
    "energy_optimization": "How plan accounts for energy level",
    "schedule": [
        {{
            "time_slot": "09:00-10:00",
            "activity": "Activity name",
            "type": "task|event|break|focus_time",
            "priority": "high/medium/low",
            "notes": "Tips for this block"
        }}
    ],
    "top_3_priorities": ["Priority 1", "Priority 2", "Priority 3"],
    "tasks_to_defer": ["Tasks that can wait"],
    "wellness_reminders": ["Take breaks", "Stay hydrated"],
    "evening_review_prompts": ["What went well?", "What to improve?"],
    "productivity_tips": ["Tip based on their situation"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"daily-plan-{uuid.uuid4()}",
            system_message="You are an AI productivity coach creating optimized daily plans. Consider human factors like energy, breaks, and realistic time estimates. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            daily_plan = json.loads(response_text)
        except Exception:
            daily_plan = {
                "date": request.date,
                "schedule": [],
                "top_3_priorities": request.goals[:3] if request.goals else ["Set your priorities"],
                "error": "Could not generate optimized plan",
            }

        # Save daily plan
        await db.daily_plans.update_one(
            {"user_id": request.user_id, "date": request.date},
            {"$set": {"plan": daily_plan, "created_at": datetime.utcnow()}},
            upsert=True,
        )

        return daily_plan

    except Exception as e:
        logger.error(f"Daily plan creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assistant/chat")
async def life_assistant_chat(request: LifeAssistantChatRequest):
    """Chat with the AI life assistant for any planning, reminders, or life help"""
    try:
        # Get user context
        tasks = await db.tasks.find({"user_id": request.user_id, "completed": False}).to_list(10)
        events_today = await db.schedule_events.find(
            {"user_id": request.user_id, "date": datetime.utcnow().strftime("%Y-%m-%d")}
        ).to_list(10)
        shopping = await db.shopping_list.find({"user_id": request.user_id, "purchased": False}).to_list(10)

        context_info = f"""
User's Current Context:
- Pending Tasks: {len(tasks)} ({", ".join([t["title"] for t in tasks[:5]])}...)
- Today's Events: {len(events_today)}
- Shopping Items: {len(shopping)} unpurchased items
- Current Time: {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}
"""

        system_prompt = f"""You are a helpful AI life assistant. You help with:
- Task management and prioritization
- Schedule and calendar planning
- Shopping list management
- Daily routine optimization
- Habit building and tracking
- Life organization and productivity

{context_info}

Be conversational, helpful, and proactive. Suggest actionable steps.
If the user wants to create tasks, events, or shopping items, confirm the details and let them know you've noted it.
Always be encouraging and supportive."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"assistant-{request.user_id}", system_message=system_prompt
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=request.message))

        # Detect if user wants to create something
        message_lower = request.message.lower()
        actions_taken = []

        if any(word in message_lower for word in ["add task", "create task", "remind me", "todo"]):
            actions_taken.append("task_suggestion")
        if any(word in message_lower for word in ["schedule", "calendar", "event", "meeting"]):
            actions_taken.append("event_suggestion")
        if any(word in message_lower for word in ["buy", "shopping", "grocery", "need to get"]):
            actions_taken.append("shopping_suggestion")

        return {
            "response": response,
            "actions_detected": actions_taken,
            "context_aware": True,
            "follow_up_suggestions": [
                "Would you like me to create a task for this?",
                "Should I add this to your schedule?",
                "Want me to add these to your shopping list?",
            ]
            if actions_taken
            else [],
        }

    except Exception as e:
        logger.error(f"Life assistant chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assistant/smart-suggestions")
async def get_smart_suggestions(user_id: str):
    """Get AI-powered suggestions based on user's patterns and data"""
    try:
        # Analyze user's data
        tasks = await db.tasks.find({"user_id": user_id}).to_list(50)
        habits = await db.habits.find({"user_id": user_id}).to_list(100)
        completed_tasks = [t for t in tasks if t.get("completed")]
        pending_tasks = [t for t in tasks if not t.get("completed")]

        # Calculate patterns
        overdue_tasks = [
            t for t in pending_tasks if t.get("due_date") and t["due_date"] < datetime.utcnow().strftime("%Y-%m-%d")
        ]

        prompt = f"""Analyze this user's productivity data and provide personalized suggestions.

Data Summary:
- Total Tasks Created: {len(tasks)}
- Completed Tasks: {len(completed_tasks)}
- Pending Tasks: {len(pending_tasks)}
- Overdue Tasks: {len(overdue_tasks)}
- Habits Tracked: {len(set(h.get("habit_name") for h in habits))}

Provide intelligent, personalized suggestions.

Return JSON:
{{
    "productivity_score": 75,
    "insights": [
        {{"insight": "Observation about their patterns", "suggestion": "How to improve"}}
    ],
    "time_saving_tips": [
        {{"tip": "Specific tip", "potential_time_saved": "X minutes/day"}}
    ],
    "habit_suggestions": [
        {{"habit": "Suggested habit", "reason": "Why it would help", "frequency": "daily/weekly"}}
    ],
    "routine_optimizations": [
        {{"current_pattern": "What they're doing", "suggested_change": "Better approach", "benefit": "Why it's better"}}
    ],
    "wellness_reminders": ["Take breaks", "Stay hydrated"],
    "motivational_message": "Personalized encouragement"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"suggestions-{uuid.uuid4()}",
            system_message="You are an AI life coach analyzing patterns and providing helpful suggestions. Be encouraging and practical. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            suggestions = json.loads(response_text)
        except Exception:
            suggestions = {
                "productivity_score": 50,
                "insights": [{"insight": "Keep tracking your tasks!", "suggestion": "Consistency is key"}],
                "motivational_message": "You're doing great! Keep it up!",
            }

        return suggestions

    except Exception as e:
        logger.error(f"Smart suggestions failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== UNIVERSAL AI TRANSLATION HUB ==============

SUPPORTED_LANGUAGES = {
    # Major World Languages
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese (Mandarin)",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    # South Asian Languages
    "bn": "Bengali",
    "pa": "Punjabi",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
    "ur": "Urdu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "or": "Odia",
    "as": "Assamese",
    "ne": "Nepali",
    "si": "Sinhala",
    "sd": "Sindhi",
    "ks": "Kashmiri",
    "sa": "Sanskrit",
    # Southeast Asian Languages
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "tl": "Filipino/Tagalog",
    "my": "Burmese",
    "km": "Khmer",
    "lo": "Lao",
    "jv": "Javanese",
    "su": "Sundanese",
    "ceb": "Cebuano",
    "hmn": "Hmong",
    # East Asian Languages
    "zh-TW": "Chinese (Traditional)",
    "yue": "Cantonese",
    "mn": "Mongolian",
    "bo": "Tibetan",
    "ug": "Uyghur",
    # African Languages
    "sw": "Swahili",
    "am": "Amharic",
    "ha": "Hausa",
    "ig": "Igbo",
    "yo": "Yoruba",
    "zu": "Zulu",
    "xh": "Xhosa",
    "af": "Afrikaans",
    "sn": "Shona",
    "so": "Somali",
    "rw": "Kinyarwanda",
    "mg": "Malagasy",
    "ny": "Chichewa",
    "st": "Sesotho",
    "tw": "Twi",
    "wo": "Wolof",
    "om": "Oromo",
    "ti": "Tigrinya",
    "lg": "Luganda",
    "ak": "Akan",
    # European Languages
    "nl": "Dutch",
    "pl": "Polish",
    "uk": "Ukrainian",
    "ro": "Romanian",
    "el": "Greek",
    "cs": "Czech",
    "hu": "Hungarian",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "tr": "Turkish",
    "he": "Hebrew",
    "fa": "Persian/Farsi",
    "bg": "Bulgarian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "hr": "Croatian",
    "sr": "Serbian",
    "bs": "Bosnian",
    "mk": "Macedonian",
    "sq": "Albanian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "mt": "Maltese",
    "is": "Icelandic",
    "ga": "Irish",
    "cy": "Welsh",
    "gd": "Scottish Gaelic",
    "eu": "Basque",
    "ca": "Catalan",
    "gl": "Galician",
    "lb": "Luxembourgish",
    "be": "Belarusian",
    # Central Asian Languages
    "kk": "Kazakh",
    "ky": "Kyrgyz",
    "uz": "Uzbek",
    "tg": "Tajik",
    "tk": "Turkmen",
    "az": "Azerbaijani",
    "hy": "Armenian",
    "ka": "Georgian",
    # Middle Eastern Languages
    "ku": "Kurdish",
    "ps": "Pashto",
    "yi": "Yiddish",
    # Pacific Languages
    "mi": "Māori",
    "haw": "Hawaiian",
    "sm": "Samoan",
    "to": "Tongan",
    "fj": "Fijian",
    # Creole & Pidgin Languages
    "ht": "Haitian Creole",
    "crs": "Seychellois Creole",
    # Ancient & Classical Languages
    "la": "Latin",
    "grc": "Ancient Greek",
    # Sign Languages (Written Form)
    "ase": "American Sign Language (written)",
    "bfi": "British Sign Language (written)",
    # Constructed Languages
    "eo": "Esperanto",
    # Regional European Languages
    "oc": "Occitan",
    "co": "Corsican",
    "br": "Breton",
    "fy": "Frisian",
    "sc": "Sardinian",
    "rm": "Romansh",
    "fur": "Friulian",
    # Additional Indian Languages
    "mai": "Maithili",
    "bho": "Bhojpuri",
    "raj": "Rajasthani",
    "kok": "Konkani",
    "doi": "Dogri",
    "mni": "Manipuri",
    "sat": "Santali",
    # Additional Asian Languages
    "tt": "Tatar",
    "ba": "Bashkir",
    "cv": "Chuvash",
    "ce": "Chechen",
    # Nordic Languages
    "fo": "Faroese",
    "kl": "Greenlandic",
    "se": "Northern Sami",
    # Other World Languages
    "fil": "Filipino",
    "tl-x-ind": "Ilocano",
    "war": "Waray",
}

# Also add to School/Learning feature
LEARNING_SUPPORTED_LANGUAGES = SUPPORTED_LANGUAGES.copy()


# ══════════ TRANSLATION ROUTES ══════════


@router.get("/translate/languages")
async def get_supported_languages():
    """Get all supported languages for translation"""
    return {"languages": SUPPORTED_LANGUAGES, "total": len(SUPPORTED_LANGUAGES)}


@router.post("/translate/text")
async def translate_text(request: TranslateTextRequest):
    """Translate text between any supported languages"""
    try:
        source_lang = SUPPORTED_LANGUAGES.get(request.source_language, request.source_language)
        target_lang = SUPPORTED_LANGUAGES.get(request.target_language, request.target_language)

        context_instruction = ""
        if request.context:
            context_instruction = (
                f"\nContext: This is {request.context} communication. Adjust formality and terminology accordingly."
            )

        prompt = f"""Translate the following text from {source_lang if request.source_language != "auto" else "the detected language"} to {target_lang}.
{context_instruction}

Text to translate:
"{request.text}"

Return JSON:
{{
    "original_text": "{request.text}",
    "translated_text": "The translation",
    "source_language": {{
        "code": "detected or specified code",
        "name": "Language name"
    }},
    "target_language": {{
        "code": "{request.target_language}",
        "name": "{target_lang}"
    }},
    "confidence": 95,
    "alternative_translations": ["Alternative 1 if applicable"],
    "cultural_notes": ["Any cultural context that might be helpful"],
    "formality_level": "formal/informal/neutral"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"translate-{uuid.uuid4()}",
            system_message="You are an expert multilingual translator. Provide accurate, natural translations that preserve meaning and tone. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            translation = json.loads(response_text)
        except Exception:
            translation = {
                "original_text": request.text,
                "translated_text": response,
                "source_language": {"code": request.source_language, "name": source_lang},
                "target_language": {"code": request.target_language, "name": target_lang},
            }

        # Save translation history
        await db.translations.insert_one(
            {"user_id": request.user_id, "translation": translation, "created_at": datetime.utcnow()}
        )

        return translation

    except Exception as e:
        logger.error(f"Translation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/translate/speech")
async def translate_speech(request: TranslateSpeechRequest):
    """Translate speech - transcribe and translate audio"""
    try:
        import base64
        import tempfile

        # Decode and save audio
        audio_data = base64.b64decode(request.audio_base64)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        # Transcribe using Whisper
        import litellm

        with open(temp_path, "rb") as audio_file:
            transcript_response = await litellm.atranscription(
                model="whisper-1", file=audio_file, api_key=EMERGENT_LLM_KEY, api_base="https://llm.emergentagi.com"
            )
        os.unlink(temp_path)

        transcribed_text = transcript_response.text

        # Now translate the transcribed text
        target_lang = SUPPORTED_LANGUAGES.get(request.target_language, request.target_language)

        prompt = f"""Translate this spoken text to {target_lang}:

"{transcribed_text}"

Make the translation natural for spoken language.

Return JSON:
{{
    "original_speech": "{transcribed_text}",
    "detected_language": "detected language",
    "translated_text": "The translation",
    "target_language": "{target_lang}",
    "pronunciation_guide": "Optional phonetic guide for the translation",
    "speaking_tips": "Tips for natural pronunciation"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"speech-translate-{uuid.uuid4()}",
            system_message="You are an expert speech translator. Make translations natural for spoken conversation. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            result = json.loads(response_text)
        except Exception:
            result = {"original_speech": transcribed_text, "translated_text": response, "target_language": target_lang}

        return result

    except Exception as e:
        logger.error(f"Speech translation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/translate/conversation/start")
async def start_translation_conversation(request: ConversationTranslateRequest):
    """Start a real-time translated conversation between two language speakers"""
    try:
        conv_id = f"trans_{str(uuid.uuid4())[:8]}"

        my_lang = SUPPORTED_LANGUAGES.get(request.my_language, request.my_language)
        their_lang = SUPPORTED_LANGUAGES.get(request.their_language, request.their_language)

        session_data = {
            "id": conv_id,
            "user_id": request.user_id,
            "my_language": {"code": request.my_language, "name": my_lang},
            "their_language": {"code": request.their_language, "name": their_lang},
            "messages": [],
            "created_at": datetime.utcnow(),
        }
        await db.translation_conversations.insert_one(session_data)

        return {
            "conversation_id": conv_id,
            "my_language": my_lang,
            "their_language": their_lang,
            "instructions": f"You speak {my_lang}. Messages will be translated to {their_lang} for the other person, and their {their_lang} messages will be translated to {my_lang} for you.",
            "ready": True,
        }

    except Exception as e:
        logger.error(f"Translation conversation start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/translate/conversation/{conv_id}/message")
async def send_translated_message(conv_id: str, user_id: str, message: str, sender: str = "me"):
    """Send a message in a translated conversation"""
    try:
        conv = await db.translation_conversations.find_one({"id": conv_id})
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Determine translation direction
        if sender == "me":
            source_lang = conv["my_language"]["name"]
            target_lang = conv["their_language"]["name"]
        else:
            source_lang = conv["their_language"]["name"]
            target_lang = conv["my_language"]["name"]

        prompt = f"""Translate this conversational message from {source_lang} to {target_lang}:

"{message}"

Keep it natural and conversational.

Return JSON:
{{
    "original": "{message}",
    "translated": "The translation",
    "tone": "detected tone of message"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"conv-translate-{conv_id}",
            system_message="You are a real-time conversation translator. Keep translations natural and conversational. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            result = json.loads(response_text)
        except Exception:
            result = {"original": message, "translated": response}

        # Save to conversation
        message_data = {
            "sender": sender,
            "original": message,
            "translated": result.get("translated", ""),
            "source_language": source_lang,
            "target_language": target_lang,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await db.translation_conversations.update_one({"id": conv_id}, {"$push": {"messages": message_data}})

        return {
            "original_message": message,
            "translated_message": result.get("translated", ""),
            "from_language": source_lang,
            "to_language": target_lang,
        }

    except Exception as e:
        logger.error(f"Translation message failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== PERSONAL HEALTH COMPANION ==============
