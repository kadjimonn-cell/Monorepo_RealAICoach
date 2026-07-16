from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid
import random
from datetime import datetime, timezone
from .db import db, logger, User, resolve_user_role
from utils.llm_helper import generate_verified_json, generate_verified_text

router = APIRouter()

DATING_DAILY_LIMITS = {
    "feed": {"free": 4, "basic": 40, "premium": -1},
    "action": {"free": 40, "basic": 300, "premium": -1},
    "message": {"free": 80, "basic": 600, "premium": -1},
}


def _resolve_dating_plan(user: User | None) -> str:
    if not user:
        return "free"
    role = resolve_user_role(user)
    if role in {"admin", "full_users", "premium"}:
        return "premium"
    if role == "basic":
        return "basic"
    return "free"


async def _enforce_dating_limit(user_id: str, action: str, plan: str) -> None:
    limit = int((DATING_DAILY_LIMITS.get(action) or DATING_DAILY_LIMITS["feed"]).get(plan, 0))
    if limit < 0:
        return

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.dating_usage_log.count_documents(
        {"user_id": user_id, "action": action, "created_at": {"$gte": start}}
    )
    if used >= limit:
        scope = "Limited access" if plan == "free" else "Almost unlimited" if plan == "basic" else "Full unlimited"
        raise HTTPException(status_code=429, detail=f"{scope}: daily dating {action} limit reached ({limit}).")


async def _log_dating_usage(user_id: str, action: str, plan: str) -> None:
    await db.dating_usage_log.insert_one(
        {
            "user_id": user_id,
            "action": action,
            "plan": plan,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

# ── Models ──


class ProfileAction(BaseModel):
    user_id: str
    target_id: str
    action: str


class ChatMessageRequest(BaseModel):
    user_id: str
    match_id: str
    message: str


# ── AI Persona Generation ──


async def generate_ai_dating_profile():
    """Generates a unique AI persona for dating using GPT-4o."""
    try:
        session_id = f"gen-date-{uuid.uuid4().hex[:8]}"
        system_msg = "You are a creative writer generating realistic dating app profiles."

        prompt = """Generate a unique, realistic dating profile for a person aged 22-35.
        Return ONLY valid JSON with keys: name, age, job, bio (max 100 chars), interests (list of 3 tags), 
        opening_line (flirty/interesting first message),
        personality_prompt (how this AI should behave in chat).
        """

        profile = await generate_verified_json(prompt, system_msg, session_id)

        # Add random photo
        profile["photos"] = [
            f"https://images.unsplash.com/photo-{random.choice(['1494790108377-be9c29b29330', '1534528741775-53994a69daeb', '1517841905240-472988babdf9', '1529626455594-4ff0802cfb7e', '1506794778202-cad84cf45f1d', '1500648767791-00dcc994a43e', '1507003211169-0a1dd7228f2d'])}?auto=format&fit=crop&w=800&q=80"
        ]
        profile["id"] = f"date_{uuid.uuid4().hex[:8]}"
        profile["match_percentage"] = random.randint(75, 99)
        profile["distance_miles"] = random.randint(1, 15)
        profile["verified"] = True

        return profile
    except Exception as e:
        logger.error(f"Profile Gen Error: {e}")
        return None


# ── Routes ──


@router.get("/dating/feed")
async def get_dating_feed(user_id: str):
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    user = User(**user_doc) if user_doc else None
    plan = _resolve_dating_plan(user)
    await _enforce_dating_limit(user_id, "feed", plan)

    profiles = []
    for _ in range(3):
        p = await generate_ai_dating_profile()
        if p:
            await db.dating_profiles.insert_one({**p})
            p.pop("_id", None)
            profiles.append(p)

    await _log_dating_usage(user_id, "feed", plan)

    return {"profiles": profiles, "plan_scope": plan}


@router.post("/dating/action")
async def dating_action(action: ProfileAction):
    user_doc = await db.users.find_one({"user_id": action.user_id}, {"_id": 0})
    user = User(**user_doc) if user_doc else None
    plan = _resolve_dating_plan(user)
    await _enforce_dating_limit(action.user_id, "action", plan)

    is_match = False
    match_data = None

    if action.action in ["like", "superlike"]:
        if random.random() > 0.2:
            is_match = True
            target_profile = await db.dating_profiles.find_one({"id": action.target_id}, {"_id": 0})

            if target_profile:
                match_id = f"match_{uuid.uuid4().hex[:8]}"
                match_data = {
                    "id": match_id,
                    "user_id": action.user_id,
                    "target_id": action.target_id,
                    "target_name": target_profile["name"],
                    "target_photo": target_profile["photos"][0],
                    "target_persona": target_profile.get("personality_prompt", "Friendly"),
                    "target_bio": target_profile.get("bio", ""),
                    "last_msg": target_profile.get("opening_line", "Hey!"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "history": [{"role": "assistant", "content": target_profile.get("opening_line", "Hey!")}],
                }
                await db.dating_matches.insert_one({**match_data})
                match_data.pop("_id", None)

    await _log_dating_usage(action.user_id, "action", plan)

    return {"success": True, "is_match": is_match, "match_details": match_data if is_match else None, "plan_scope": plan}


@router.get("/dating/matches/{user_id}")
async def get_matches(user_id: str):
    matches = await db.dating_matches.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"matches": matches}


@router.post("/dating/message")
async def send_dating_message(request: ChatMessageRequest):
    user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
    user = User(**user_doc) if user_doc else None
    plan = _resolve_dating_plan(user)
    await _enforce_dating_limit(request.user_id, "message", plan)

    match = await db.dating_matches.find_one({"id": request.match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    new_history = match.get("history", [])
    new_history.append({"role": "user", "content": request.message})

    try:
        persona = match.get("target_persona", "Friendly and engaging")
        name = match.get("target_name", "Match")

        system_msg = f"""You are {name}. {persona}
        You are chatting with a match on a dating app.
        Keep messages short (1-3 sentences), engaging, and casual.
        Match's Bio: {match.get("target_bio")}
        """

        session_id = f"dating-chat-{request.match_id}"
        # Use verified text generation for better quality
        ai_text = await generate_verified_text(request.message, system_msg, session_id)

        new_history.append({"role": "assistant", "content": ai_text})

        await db.dating_matches.update_one(
            {"id": request.match_id},
            {
                "$set": {
                    "history": new_history,
                    "last_msg": ai_text,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        await _log_dating_usage(request.user_id, "message", plan)
        return {"response": ai_text, "history": new_history, "plan_scope": plan}

    except Exception as e:
        logger.error(f"Dating Chat Error: {e}")
        return {"response": "Haha, that's interesting! Tell me more.", "history": new_history}


@router.get("/dating/chat/{match_id}")
async def get_chat_history(match_id: str):
    match = await db.dating_matches.find_one({"id": match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return {"history": match.get("history", []), "match": match}
