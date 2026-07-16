"""Feature 37 — Flappy Bird Game.

Web-native port of ellisonleao/clumsy-bird (MIT licensed, MelonJS 2.x)
integrated into the RealAICoach platform. The legacy MelonJS runtime is
incompatible with the Metro/React-Native-Web bundle (global `me` namespace,
Number.prototype monkey-patching), so the game logic was faithfully ported
to an isolated Canvas-2D React component while reusing the original art and
sound assets. This router persists scores, serves all-time + weekly
leaderboards, tracks daily challenges/streaks and awards platform XP.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from .db import db, require_admin, require_auth
from .gamification import add_xp

router = APIRouter(prefix="/flappy-bird", tags=["Flappy Bird Game"])

MAX_REASONABLE_SCORE = 9999
LEADERBOARD_LIMIT = 10
DIFFICULTIES = ("easy", "classic", "hard")
XP_PER_RUN_CAP = 30
XP_DAILY_CAP = 100
XP_DAILY_CHALLENGE_BONUS = 20

MEDAL_THRESHOLDS = (
    (100, "diamond"),
    (50, "gold"),
    (25, "silver"),
    (10, "bronze"),
)


class ScoreSubmission(BaseModel):
    score: int = Field(..., ge=0, le=MAX_REASONABLE_SCORE)
    duration_ms: int = Field(default=0, ge=0, le=86_400_000)
    difficulty: str = Field(default="classic")

    @field_validator("difficulty")
    @classmethod
    def _valid_difficulty(cls, v: str) -> str:
        v = str(v or "classic").lower().strip()
        return v if v in DIFFICULTIES else "classic"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _day_key(d: date | None = None) -> str:
    return (d or _today()).isoformat()


def _week_key(d: date | None = None) -> str:
    d = d or _today()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def medal_for_score(score: int) -> str:
    for threshold, medal in MEDAL_THRESHOLDS:
        if score >= threshold:
            return medal
    return "none"


def daily_challenge_target(d: date | None = None) -> int:
    d = d or _today()
    seed = d.toordinal()
    return 5 + (seed % 3) * 5  # deterministic 5 / 10 / 15 rotation


async def _personal_stats(user_id: str) -> dict[str, Any]:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": {"$ifNull": ["$difficulty", "classic"]},
            "best": {"$max": "$score"},
            "games": {"$sum": 1},
        }},
    ]
    rows = await db.flappy_bird_scores.aggregate(pipeline).to_list(10)
    per_difficulty = {diff: 0 for diff in DIFFICULTIES}
    best = 0
    games = 0
    for row in rows:
        diff = str(row.get("_id") or "classic")
        diff_best = int(row.get("best") or 0)
        if diff in per_difficulty:
            per_difficulty[diff] = diff_best
        best = max(best, diff_best)
        games += int(row.get("games") or 0)
    return {"personal_best": best, "games_played": games, "best_by_difficulty": per_difficulty}


async def _leaderboard(scope: str = "all_time", limit: int = LEADERBOARD_LIMIT) -> list[dict[str, Any]]:
    match: dict[str, Any] = {}
    if scope == "weekly":
        match = {"week_key": _week_key()}
    pipeline: list[dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$group": {
            "_id": "$user_id",
            "best_score": {"$max": "$score"},
            "display_name": {"$last": "$display_name"},
            "games_played": {"$sum": 1},
            "last_played_at": {"$max": "$created_at"},
        }},
        {"$sort": {"best_score": -1, "last_played_at": 1}},
        {"$limit": max(1, min(50, limit))},
    ]
    rows = await db.flappy_bird_scores.aggregate(pipeline).to_list(50)
    return [
        {
            "rank": idx + 1,
            "user_id": str(row.get("_id") or ""),
            "display_name": str(row.get("display_name") or "Player"),
            "best_score": int(row.get("best_score") or 0),
            "games_played": int(row.get("games_played") or 0),
            "medal": medal_for_score(int(row.get("best_score") or 0)),
        }
        for idx, row in enumerate(rows)
    ]


async def _my_rank(user_id: str, scope: str = "all_time") -> dict[str, Any]:
    match: dict[str, Any] = {}
    if scope == "weekly":
        match = {"week_key": _week_key()}
    pipeline: list[dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$group": {"_id": "$user_id", "best_score": {"$max": "$score"}}},
        {"$sort": {"best_score": -1}},
    ]
    rows = await db.flappy_bird_scores.aggregate(pipeline).to_list(5000)
    for idx, row in enumerate(rows):
        if str(row.get("_id")) == user_id:
            return {"rank": idx + 1, "best_score": int(row.get("best_score") or 0), "total_players": len(rows)}
    return {"rank": 0, "best_score": 0, "total_players": len(rows)}


async def _daily_challenge_state(user_id: str) -> dict[str, Any]:
    today = _today()
    target = daily_challenge_target(today)
    docs = await (
        db.flappy_bird_daily
        .find({"user_id": user_id}, {"_id": 0, "day_key": 1})
        .sort("day_key", -1)
        .to_list(400)
    )
    completed_days = {str(d.get("day_key")) for d in docs}
    completed_today = _day_key(today) in completed_days
    streak = 0
    cursor = today if completed_today else today - timedelta(days=1)
    while _day_key(cursor) in completed_days:
        streak += 1
        cursor -= timedelta(days=1)
    return {"target": target, "completed_today": completed_today, "streak": streak}


async def _xp_earned_today(user_id: str) -> int:
    pipeline = [
        {"$match": {"user_id": user_id, "day_key": _day_key()}},
        {"$group": {"_id": None, "xp": {"$sum": {"$ifNull": ["$xp_awarded", 0]}}}},
    ]
    rows = await db.flappy_bird_scores.aggregate(pipeline).to_list(1)
    return int(rows[0].get("xp") or 0) if rows else 0


async def _payload_common(user_id: str) -> dict[str, Any]:
    return {
        "leaderboard": await _leaderboard("all_time"),
        "weekly_leaderboard": await _leaderboard("weekly"),
        "my_rank": await _my_rank(user_id, "all_time"),
        "my_weekly_rank": await _my_rank(user_id, "weekly"),
        "daily_challenge": await _daily_challenge_state(user_id),
        "xp": {"earned_today": await _xp_earned_today(user_id), "daily_cap": XP_DAILY_CAP, "per_run_cap": XP_PER_RUN_CAP},
    }


@router.get("/bootstrap")
async def flappy_bootstrap(request: Request):
    user = await require_auth(request)
    stats = await _personal_stats(user.user_id)
    return {
        "feature_id": "flappy-bird",
        "title": "Flappy Bird Game",
        **stats,
        **(await _payload_common(user.user_id)),
        "max_score": MAX_REASONABLE_SCORE,
        "difficulties": list(DIFFICULTIES),
        "week_key": _week_key(),
    }


@router.post("/admin/streak-saver-run")
async def flappy_streak_saver_run(request: Request):
    """Admin-only manual trigger for the streak-saver email job."""
    await require_admin(request)
    from services.flappy_streak_saver import send_streak_saver_reminders, find_at_risk_users

    at_risk = await find_at_risk_users()
    sent = await send_streak_saver_reminders()
    return {"at_risk_count": len(at_risk), "emails_sent": sent, "day_key": _day_key()}


@router.get("/daily-challenge")
async def flappy_daily_challenge(request: Request):
    """Lightweight daily-challenge summary for the home dashboard card."""
    user = await require_auth(request)
    stats = await _personal_stats(user.user_id)
    return {
        **(await _daily_challenge_state(user.user_id)),
        "personal_best": stats["personal_best"],
    }


@router.get("/leaderboard")
async def flappy_leaderboard(request: Request, limit: int = LEADERBOARD_LIMIT, scope: str = "all_time"):
    await require_auth(request)
    scope = scope if scope in ("all_time", "weekly") else "all_time"
    return {"scope": scope, "leaderboard": await _leaderboard(scope, limit)}


@router.post("/score")
async def flappy_submit_score(request: Request, payload: ScoreSubmission):
    user = await require_auth(request)
    previous = await _personal_stats(user.user_id)
    score = int(payload.score)
    difficulty = payload.difficulty

    xp_today = await _xp_earned_today(user.user_id)
    xp_award = min(score, XP_PER_RUN_CAP, max(0, XP_DAILY_CAP - xp_today))

    challenge_before = await _daily_challenge_state(user.user_id)
    challenge_completed_now = (
        not challenge_before["completed_today"] and score >= challenge_before["target"]
    )
    if challenge_completed_now:
        await db.flappy_bird_daily.update_one(
            {"user_id": user.user_id, "day_key": _day_key()},
            {"$setOnInsert": {
                "user_id": user.user_id,
                "day_key": _day_key(),
                "target": challenge_before["target"],
                "score": score,
                "completed_at": _iso_now(),
            }},
            upsert=True,
        )
        xp_award += XP_DAILY_CHALLENGE_BONUS

    doc = {
        "run_id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "display_name": (user.name or user.email.split("@")[0])[:32],
        "score": score,
        "duration_ms": int(payload.duration_ms),
        "difficulty": difficulty,
        "medal": medal_for_score(score),
        "week_key": _week_key(),
        "day_key": _day_key(),
        "xp_awarded": xp_award,
        "created_at": _iso_now(),
    }
    await db.flappy_bird_scores.insert_one(doc)

    if xp_award > 0:
        try:
            await add_xp(user.user_id, xp_award, reason="flappy_bird")
        except Exception:
            pass  # XP is best-effort; the run itself is already persisted

    stats = await _personal_stats(user.user_id)
    return {
        "accepted": True,
        "score": score,
        "difficulty": difficulty,
        "medal": medal_for_score(score),
        "is_new_best": score > int(previous["personal_best"]),
        "is_new_difficulty_best": score > int(previous["best_by_difficulty"].get(difficulty, 0)),
        "xp_awarded": xp_award,
        "daily_challenge_completed_now": challenge_completed_now,
        **stats,
        **(await _payload_common(user.user_id)),
    }
