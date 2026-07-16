"""AI Coaching Team — Feature 31. Premium user-facing coaching chat.

Curated coaches from the native agent framework (memory, quotas, audit built in):
Career Coach, Interview Coach, Resume Specialist, Negotiation Coach.

Replaces the retired Problem Solver (see routes/ai_problem_solver.py retirement stub).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, get_current_user
from utils.access_control_engine import build_feature_entitlements, compute_effective_plan

router = APIRouter(prefix="/ai-coaching-team")

COACH_KEYS = ["career_coach", "interview_coach", "resume_specialist", "negotiation_coach"]
FREE_TIER_COACHES = {"career_coach"}

COACH_META = {
    "career_coach": {"icon": "compass", "color": "#0F766E", "tagline": "Career growth & direction"},
    "interview_coach": {"icon": "mic", "color": "#2563EB", "tagline": "Mock interviews & STAR feedback"},
    "resume_specialist": {"icon": "document-text", "color": "#D97706", "tagline": "Resume & profile optimization"},
    "negotiation_coach": {"icon": "trending-up", "color": "#7C3AED", "tagline": "Salary & offer negotiation"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _require_user(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _tier_of(user) -> str:
    if user.is_admin or getattr(user, "full_access", False):
        return "premium"
    return compute_effective_plan(user.model_dump())


def _entitlements(tier: str) -> dict:
    ent = build_feature_entitlements(tier)
    return {
        "daily_messages": ent.get("coaching_team_daily_messages", 5),
        "all_coaches": bool(ent.get("coaching_team_all_coaches", False)),
    }


async def _messages_used_today(user_id: str) -> int:
    doc = await db.coaching_team_usage.find_one({"user_id": user_id, "date": _today()}, {"_id": 0})
    return int((doc or {}).get("count", 0))


def _coach_allowed(coach_key: str, ent: dict) -> bool:
    return ent["all_coaches"] or coach_key in FREE_TIER_COACHES


async def _preview_used(user_id: str, coach_key: str) -> bool:
    doc = await db.coaching_team_previews.find_one(
        {"user_id": user_id, "coach_key": coach_key}, {"_id": 0}
    )
    return doc is not None


class CreateSessionRequest(BaseModel):
    coach_key: str


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


@router.get("/coaches")
async def list_coaches(request: Request):
    from agent_framework.agents import get_agent

    user = await _require_user(request)
    tier = _tier_of(user)
    ent = _entitlements(tier)
    coaches = []
    for key in COACH_KEYS:
        agent = await get_agent(key)
        if not agent or not agent.get("enabled", True):
            continue
        available = _coach_allowed(key, ent)
        coaches.append({
            "coach_key": key,
            "name": agent["name"],
            "role": agent.get("role", ""),
            "description": agent.get("description", ""),
            **COACH_META.get(key, {}),
            "available": available,
            "preview_available": (not available) and not await _preview_used(user.user_id, key),
        })
    return {"coaches": coaches, "tier": tier, "all_coaches_unlocked": ent["all_coaches"]}


@router.get("/status")
async def coaching_status(request: Request):
    user = await _require_user(request)
    tier = _tier_of(user)
    ent = _entitlements(tier)
    used = await _messages_used_today(user.user_id)
    limit = ent["daily_messages"]
    return {
        "tier": tier,
        "daily_limit": limit,
        "used_today": used,
        "remaining_today": -1 if limit == -1 else max(0, int(limit) - used),
        "all_coaches_unlocked": ent["all_coaches"],
    }


@router.get("/sessions")
async def list_sessions(request: Request):
    user = await _require_user(request)
    items = await (
        db.coaching_team_sessions
        .find({"user_id": user.user_id}, {"_id": 0, "messages": 0})
        .sort("updated_at", -1).limit(50).to_list(length=50)
    )
    return {"sessions": items}


@router.post("/sessions")
async def create_session(payload: CreateSessionRequest, request: Request):
    from agent_framework.agents import get_agent

    user = await _require_user(request)
    if payload.coach_key not in COACH_KEYS:
        raise HTTPException(status_code=400, detail="Unknown coach")
    ent = _entitlements(_tier_of(user))
    is_preview = False
    if not _coach_allowed(payload.coach_key, ent):
        if await _preview_used(user.user_id, payload.coach_key):
            raise HTTPException(status_code=402, detail={
                "code": "COACH_LOCKED",
                "message": "This coach is available on Basic and Premium plans.",
                "upgrade_route": "/subscription/plans",
            })
        is_preview = True
    agent = await get_agent(payload.coach_key)
    if not agent:
        raise HTTPException(status_code=404, detail="Coach not found")
    session = {
        "session_id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "coach_key": payload.coach_key,
        "coach_name": agent["name"],
        "title": f"{agent['name']} session",
        "is_preview": is_preview,
        "messages": [],
        "message_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.coaching_team_sessions.insert_one(dict(session))
    session.pop("_id", None)
    return session


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    user = await _require_user(request)
    session = await db.coaching_team_sessions.find_one(
        {"session_id": session_id, "user_id": user.user_id}, {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    ent = _entitlements(_tier_of(user))
    session["preview_gate"] = bool(
        session.get("is_preview")
        and not _coach_allowed(session["coach_key"], ent)
        and await _preview_used(user.user_id, session["coach_key"])
    )
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    user = await _require_user(request)
    result = await db.coaching_team_sessions.delete_one(
        {"session_id": session_id, "user_id": user.user_id}
    )
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, payload: SendMessageRequest, request: Request):
    from agent_framework.agents import get_agent, execute_agent

    user = await _require_user(request)
    session = await db.coaching_team_sessions.find_one(
        {"session_id": session_id, "user_id": user.user_id}, {"_id": 0, "messages": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    ent = _entitlements(_tier_of(user))
    is_preview_message = False
    if not _coach_allowed(session["coach_key"], ent):
        if not session.get("is_preview") or await _preview_used(user.user_id, session["coach_key"]):
            raise HTTPException(status_code=402, detail={
                "code": "PREVIEW_USED" if session.get("is_preview") else "COACH_LOCKED",
                "message": "Your free preview with this coach has been used. Upgrade to keep coaching."
                if session.get("is_preview")
                else "This coach is available on Basic and Premium plans.",
                "upgrade_route": "/subscription/plans",
            })
        is_preview_message = True
    limit = ent["daily_messages"]
    used = await _messages_used_today(user.user_id)
    if limit != -1 and used >= int(limit):
        raise HTTPException(status_code=429, detail={
            "code": "DAILY_LIMIT_REACHED",
            "message": "Daily coaching message limit reached. Upgrade for unlimited coaching.",
            "daily_limit": limit,
            "upgrade_route": "/subscription/plans",
        })

    agent = await get_agent(session["coach_key"])
    if not agent or not agent.get("enabled", True):
        raise HTTPException(status_code=503, detail="Coach temporarily unavailable")

    try:
        result = await execute_agent(
            agent, payload.message,
            session_id=f"ct-{session_id}", user_id=user.user_id, timeout_seconds=60,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Coach response timed out. Please try again.")

    now = _now()
    new_messages = [
        {"role": "user", "content": payload.message, "at": now},
        {"role": "assistant", "content": result["output"], "at": now},
    ]
    await db.coaching_team_sessions.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"$each": new_messages, "$slice": -200}},
            "$inc": {"message_count": 1},
            "$set": {"updated_at": now},
        },
    )
    await db.coaching_team_usage.update_one(
        {"user_id": user.user_id, "date": _today()},
        {"$inc": {"count": 1}, "$set": {"updated_at": now}},
        upsert=True,
    )
    if is_preview_message:
        await db.coaching_team_previews.update_one(
            {"user_id": user.user_id, "coach_key": session["coach_key"]},
            {"$setOnInsert": {"used_at": now, "session_id": session_id}},
            upsert=True,
        )
    remaining = -1 if limit == -1 else max(0, int(limit) - used - 1)
    return {
        "reply": result["output"],
        "remaining_today": remaining,
        "preview_used": is_preview_message,
        "preview_gate": is_preview_message,
    }

@router.post("/digest/run")
async def run_coaching_digest(request: Request, dry_run: bool = True):
    """Admin-only: trigger the weekly coaching digest (dry_run=true previews recipients without sending)."""
    from routes.db import require_admin
    from services.coaching_team_digest import send_coaching_team_weekly_digest

    await require_admin(request)
    return await send_coaching_team_weekly_digest(
        trigger="manual_admin", dry_run=dry_run
    )

@router.post("/digest/push/run")
async def run_coaching_digest_push(request: Request, dry_run: bool = True):
    """Admin-only: trigger the daily coaching push digest (dry_run=true previews recipients without sending)."""
    from routes.db import require_admin
    from services.coaching_digest_push import send_coaching_daily_digest_push

    await require_admin(request)
    return await send_coaching_daily_digest_push(trigger="manual_admin", dry_run=dry_run)

@router.get("/digest/push/runs")
async def list_coaching_digest_push_runs(request: Request, limit: int = 10):
    """Admin-only: recent daily push digest run summaries."""
    from routes.db import require_admin

    await require_admin(request)
    runs = await db.coaching_digest_push_runs.find({}, {"_id": 0}).sort(
        "finished_at", -1
    ).to_list(length=min(limit, 50))
    return {"runs": runs}
