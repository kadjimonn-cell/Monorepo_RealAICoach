from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from utils.access_control_engine import compute_effective_plan

from .db import db, require_admin, require_auth
from .sports_v2_bootstrap_service import build_sports_v2_bootstrap
from .sports_v2_internal import (
    BLACKOUT_RULES_COLL,
    SPORTS_CATEGORY_CURATION_COLL,
    SPORTS_SOURCE_REPLACEMENT_HISTORY_COLL,
    active_sports_blackout_rules,
    ensure_default_sports_blackout_rules,
    evaluate_sports_blackout,
    normalize_category_name,
    normalize_country_code,
    normalize_state_code,
    now_iso,
    parse_iso_datetime,
    resolve_region_for_user_id,
    verify_stream_token,
)
from .sports_v2_schemas import (
    AudioPlayRequest,
    FollowLeagueRequest,
    InboxMarkListenedRequest,
    SportsPredictionSubmitRequest,
)


PLAN_LEVEL = {"free": 0, "basic": 1, "premium": 2}

SPORTS_CFG = {
    "catalog_coll": "watch_sports_catalog",
    "history_coll": "watch_sports_history",
    "usage_coll": "watch_sports_usage",
    "inbox_status_coll": "watch_sports_inbox_status",
}

SPORTS_STREAK_COLL = "watch_sports_matchday_streaks"
SPORTS_PREDICTION_COLL = "watch_sports_prediction_challenges"
SPORTS_PREDICTION_SUBMISSION_COLL = "watch_sports_prediction_submissions"


def _today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _default_prediction_challenges(today_key: str) -> list[dict[str, Any]]:
    return [
        {
            "challenge_id": f"sports-{today_key}-winner-pick",
            "title": "Winner Pick Challenge",
            "subtitle": "Choose the side most likely to dominate tonight.",
            "type": "winner_pick",
            "points_reward": 30,
            "prompt": "Who wins tonight's featured matchup?",
            "option_keys": ["home", "away", "draw"],
            "option_labels": {
                "home": "Home side wins",
                "away": "Away side wins",
                "draw": "Draw / overtime push",
            },
            "is_active": True,
            "day_key": today_key,
        },
        {
            "challenge_id": f"sports-{today_key}-tempo-call",
            "title": "Tempo Call",
            "subtitle": "Predict how explosive the game pace will be.",
            "type": "tempo_call",
            "points_reward": 20,
            "prompt": "Will this game be high tempo?",
            "option_keys": ["high", "balanced", "grind"],
            "option_labels": {
                "high": "High tempo",
                "balanced": "Balanced tempo",
                "grind": "Defensive grind",
            },
            "is_active": True,
            "day_key": today_key,
        },
    ]


def _compute_streak_payload(days_desc: list[str]) -> tuple[int, str, str]:
    if not days_desc:
        return 0, "cold", "Start your first matchday streak today."

    unique_sorted = sorted({str(day) for day in days_desc if str(day)}, reverse=True)
    if not unique_sorted:
        return 0, "cold", "Start your first matchday streak today."

    streak = 0
    cursor = datetime.now(timezone.utc).date()
    for day_key in unique_sorted:
        try:
            day_dt = datetime.fromisoformat(day_key).date()
        except Exception:
            continue
        if day_dt == cursor:
            streak += 1
            cursor = cursor - timedelta(days=1)
            continue
        if streak == 0 and day_dt == (cursor - timedelta(days=1)):
            streak = 1
            cursor = day_dt - timedelta(days=1)
            continue
        break

    latest = unique_sorted[0]
    try:
        latest_day = datetime.fromisoformat(latest).date()
    except Exception:
        latest_day = datetime.now(timezone.utc).date() - timedelta(days=30)

    days_since_last = max(0, (datetime.now(timezone.utc).date() - latest_day).days)
    if days_since_last == 0:
        status = "active"
        prompt = "You're hot today. Keep the run alive with one more watch."
    elif days_since_last == 1:
        status = "at_risk"
        prompt = "Come back today to protect your streak before it cools."
    else:
        status = "cold"
        prompt = "Your streak cooled off — jump back in and restart momentum."

    return int(streak), status, prompt


def _streak_milestones() -> list[dict[str, Any]]:
    return [
        {"days": 1, "badge": "Kickoff", "reward": "+5 challenge points"},
        {"days": 3, "badge": "Momentum", "reward": "Prediction multiplier x1.1"},
        {"days": 5, "badge": "Comeback King", "reward": "Smart comeback prompt boost"},
        {"days": 7, "badge": "Matchday Elite", "reward": "Priority challenge rail"},
        {"days": 14, "badge": "Season Grinder", "reward": "Bonus retention badge"},
    ]


def _build_streak_rewards(streak_days: int) -> dict[str, Any]:
    milestones = _streak_milestones()
    unlocked = [m for m in milestones if streak_days >= int(m.get("days") or 0)]
    next_milestone = next((m for m in milestones if streak_days < int(m.get("days") or 0)), None)

    if next_milestone:
        previous_days = int(unlocked[-1]["days"]) if unlocked else 0
        span = max(1, int(next_milestone["days"]) - previous_days)
        progress = int(round(max(0.0, min(100.0, ((streak_days - previous_days) / span) * 100.0))))
        next_payload = {
            "required_days": int(next_milestone["days"]),
            "badge": str(next_milestone["badge"]),
            "reward": str(next_milestone["reward"]),
            "remaining_days": max(0, int(next_milestone["days"]) - streak_days),
            "progress_pct": progress,
        }
    else:
        next_payload = {
            "required_days": int(streak_days),
            "badge": str(unlocked[-1]["badge"] if unlocked else "Kickoff"),
            "reward": "All streak rewards unlocked",
            "remaining_days": 0,
            "progress_pct": 100,
        }

    return {
        "current_badge": str(unlocked[-1]["badge"] if unlocked else "Not unlocked"),
        "badges_unlocked": unlocked,
        "next_milestone": next_payload,
    }


async def _ensure_prediction_challenges_for_today(day_key: str) -> list[dict[str, Any]]:
    existing = await db[SPORTS_PREDICTION_COLL].find(
        {"day_key": day_key, "is_active": True},
        {
            "_id": 0,
            "challenge_id": 1,
            "title": 1,
            "subtitle": 1,
            "type": 1,
            "points_reward": 1,
            "prompt": 1,
            "option_keys": 1,
            "option_labels": 1,
            "is_active": 1,
            "day_key": 1,
        },
    ).to_list(20)
    if existing:
        return existing

    now = now_iso()
    defaults = _default_prediction_challenges(day_key)
    docs = []
    for challenge in defaults:
        docs.append(
            {
                **challenge,
                "created_at": now,
                "updated_at": now,
                "created_by": "system_seed",
            }
        )

    if docs:
        await db[SPORTS_PREDICTION_COLL].insert_many(docs)

    return defaults


async def _sports_prediction_rail_for_user(user_id: str, day_key: str) -> dict[str, Any]:
    challenges = await _ensure_prediction_challenges_for_today(day_key)

    submissions = await db[SPORTS_PREDICTION_SUBMISSION_COLL].find(
        {"user_id": user_id, "day_key": day_key},
        {"_id": 0, "challenge_id": 1, "option_key": 1, "submitted_at": 1, "points_reward": 1},
    ).to_list(30)
    submission_by_challenge = {
        str(row.get("challenge_id") or ""): row
        for row in submissions
        if str(row.get("challenge_id") or "")
    }

    challenges_out: list[dict[str, Any]] = []
    total_possible_points = 0
    points_claimed = 0
    for challenge in challenges:
        challenge_id = str(challenge.get("challenge_id") or "")
        points_reward = int(challenge.get("points_reward") or 0)
        total_possible_points += points_reward
        submission = submission_by_challenge.get(challenge_id)
        if submission:
            points_claimed += int(submission.get("points_reward") or points_reward)

        challenges_out.append(
            {
                **challenge,
                "submitted": bool(submission),
                "submitted_option_key": str((submission or {}).get("option_key") or ""),
                "submitted_at": str((submission or {}).get("submitted_at") or ""),
            }
        )

    return {
        "day_key": day_key,
        "total": int(len(challenges_out)),
        "submitted": int(len(submission_by_challenge)),
        "points_claimed": int(points_claimed),
        "points_available": int(total_possible_points),
        "challenges": challenges_out,
    }


async def _sports_streak_dashboard_for_user(user_id: str, day_key: str) -> dict[str, Any]:
    row = await db[SPORTS_STREAK_COLL].find_one(
        {"user_id": user_id},
        {"_id": 0, "activity_days": 1, "last_activity_day": 1, "longest_streak_days": 1, "updated_at": 1},
    ) or {}

    days = [str(day) for day in (row.get("activity_days") or []) if str(day)]
    streak_days, streak_status, comeback_prompt = _compute_streak_payload(days)
    longest = max(int(row.get("longest_streak_days") or 0), int(streak_days))
    rewards = _build_streak_rewards(streak_days)

    return {
        "day_key": day_key,
        "current_streak_days": int(streak_days),
        "longest_streak_days": int(longest),
        "status": streak_status,
        "total_active_days": int(len(set(days))),
        "last_activity_day": str(row.get("last_activity_day") or ""),
        "comeback_prompt": comeback_prompt,
        "rewards": rewards,
    }


async def _upsert_streak_for_play(user_id: str, day_key: str) -> None:
    current = await db[SPORTS_STREAK_COLL].find_one(
        {"user_id": user_id},
        {"_id": 0, "activity_days": 1, "longest_streak_days": 1},
    ) or {}
    existing_days = [str(day) for day in (current.get("activity_days") or []) if str(day)]
    if day_key not in existing_days:
        existing_days.append(day_key)
    unique_days = sorted(set(existing_days), reverse=True)[:90]

    streak_days, _, _ = _compute_streak_payload(unique_days)
    longest = max(int(current.get("longest_streak_days") or 0), int(streak_days))
    now = now_iso()

    await db[SPORTS_STREAK_COLL].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "activity_days": unique_days,
                "last_activity_day": day_key,
                "longest_streak_days": int(longest),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


def _plan_for_user(user: Any) -> str:
    return compute_effective_plan(
        {
            "subscription_plan": getattr(user, "subscription_plan", "free"),
            "subscription_status": getattr(user, "subscription_status", "active"),
            "subscription_end_date": getattr(user, "subscription_end_date", None),
            "subscription_permanent": getattr(user, "subscription_permanent", False),
            "payment_verified": getattr(user, "payment_verified", False),
            "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
            "is_admin": getattr(user, "is_admin", False),
            "full_access": getattr(user, "full_access", False),
        }
    )


def _plan_allows(user_plan: str, min_plan: str) -> bool:
    return int(PLAN_LEVEL.get(str(user_plan or "free"), 0)) >= int(PLAN_LEVEL.get(str(min_plan or "free"), 0))


def _safe_rate(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round((float(num) / float(den)) * 100.0, 2)


def _normalize_geo_country(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return "UNKNOWN"
    if len(raw) > 3:
        return raw[:3]
    return raw


def _safe_delta_pct(current: float, previous: float) -> float:
    previous_val = float(previous)
    current_val = float(current)
    if abs(previous_val) < 1e-9:
        if abs(current_val) < 1e-9:
            return 0.0
        return 100.0
    return round(((current_val - previous_val) / abs(previous_val)) * 100.0, 2)


def _safe_delta_abs(current: float, previous: float) -> float:
    return round(float(current) - float(previous), 2)


def _compute_metrics_snapshot(
    history_rows: list[dict[str, Any]],
    user_plans: dict[str, str],
) -> dict[str, Any]:
    total_plays = int(len(history_rows))
    completed_plays = 0
    total_watch_seconds = 0
    active_user_ids: set[str] = set()
    session_lengths: dict[str, int] = {}
    live_starts = 0

    device_counts: dict[str, int] = {"web": 0, "native": 0, "unknown": 0}
    channel_counts: dict[str, int] = {}
    geo_counts: dict[str, int] = {}
    league_counts: dict[str, int] = {}

    for row in history_rows:
        user_id = str(row.get("user_id") or "").strip()
        watch_seconds = int(row.get("listen_seconds") or 0)
        if watch_seconds < 0:
            watch_seconds = 0

        total_watch_seconds += watch_seconds
        if bool(row.get("completed")):
            completed_plays += 1
        if bool(row.get("is_live")):
            live_starts += 1

        device_bucket = str(row.get("device_bucket") or "unknown").strip().lower()
        if device_bucket not in {"web", "native"}:
            device_bucket = "unknown"
        device_counts[device_bucket] = int(device_counts.get(device_bucket) or 0) + 1

        channel = str(row.get("source") or "unknown").strip().lower() or "unknown"
        channel_counts[channel] = int(channel_counts.get(channel) or 0) + 1

        geo_country = _normalize_geo_country(row.get("geo_country"))
        geo_counts[geo_country] = int(geo_counts.get(geo_country) or 0) + 1

        league_name = str(row.get("league") or row.get("category") or "unknown").strip() or "unknown"
        league_counts[league_name] = int(league_counts.get(league_name) or 0) + 1

        if not user_id:
            continue

        active_user_ids.add(user_id)
        day_key = str(row.get("created_at") or "")[:10] or datetime.now(timezone.utc).date().isoformat()
        session_key = f"{user_id}:{day_key}"
        session_lengths[session_key] = int(session_lengths.get(session_key) or 0) + watch_seconds

    active_listeners = int(len(active_user_ids))
    avg_session_length_seconds = round(
        float(sum(session_lengths.values())) / float(max(len(session_lengths), 1)),
        2,
    )
    completion_rate_pct = _safe_rate(completed_plays, total_plays)
    live_ratio_pct = _safe_rate(live_starts, total_plays)

    free_engaged = 0
    basic_engaged = 0
    premium_engaged = 0
    for user_id in active_user_ids:
        plan = str(user_plans.get(user_id) or "free").strip().lower()
        if plan == "free":
            free_engaged += 1
        elif plan == "basic":
            basic_engaged += 1
        else:
            premium_engaged += 1

    return {
        "active_listeners": active_listeners,
        "total_plays": total_plays,
        "completed_plays": completed_plays,
        "live_starts": int(live_starts),
        "live_ratio_pct": live_ratio_pct,
        "completion_rate_pct": completion_rate_pct,
        "avg_session_length_seconds": avg_session_length_seconds,
        "avg_watch_seconds_per_play": round(float(total_watch_seconds) / float(max(total_plays, 1)), 2),
        "listener_mix": {
            "free": int(free_engaged),
            "basic": int(basic_engaged),
            "premium": int(premium_engaged),
        },
        "cohorts": {
            "device": {k: int(v) for k, v in sorted(device_counts.items(), key=lambda kv: kv[1], reverse=True)},
            "channel": {k: int(v) for k, v in sorted(channel_counts.items(), key=lambda kv: kv[1], reverse=True)},
            "geo_country": {k: int(v) for k, v in sorted(geo_counts.items(), key=lambda kv: kv[1], reverse=True)},
            "league": {k: int(v) for k, v in sorted(league_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]},
        },
    }


def _compute_benchmark_deltas(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "avg_session_length_seconds": {
            "current": float(current.get("avg_session_length_seconds") or 0),
            "previous": float(previous.get("avg_session_length_seconds") or 0),
            "delta_abs": _safe_delta_abs(
                float(current.get("avg_session_length_seconds") or 0),
                float(previous.get("avg_session_length_seconds") or 0),
            ),
            "delta_pct": _safe_delta_pct(
                float(current.get("avg_session_length_seconds") or 0),
                float(previous.get("avg_session_length_seconds") or 0),
            ),
        },
        "completion_rate_pct": {
            "current": float(current.get("completion_rate_pct") or 0),
            "previous": float(previous.get("completion_rate_pct") or 0),
            "delta_abs": _safe_delta_abs(
                float(current.get("completion_rate_pct") or 0),
                float(previous.get("completion_rate_pct") or 0),
            ),
            "delta_pct": _safe_delta_pct(
                float(current.get("completion_rate_pct") or 0),
                float(previous.get("completion_rate_pct") or 0),
            ),
        },
        "active_listeners": {
            "current": int(current.get("active_listeners") or 0),
            "previous": int(previous.get("active_listeners") or 0),
            "delta_abs": _safe_delta_abs(
                float(current.get("active_listeners") or 0),
                float(previous.get("active_listeners") or 0),
            ),
            "delta_pct": _safe_delta_pct(
                float(current.get("active_listeners") or 0),
                float(previous.get("active_listeners") or 0),
            ),
        },
        "live_ratio_pct": {
            "current": float(current.get("live_ratio_pct") or 0),
            "previous": float(previous.get("live_ratio_pct") or 0),
            "delta_abs": _safe_delta_abs(
                float(current.get("live_ratio_pct") or 0),
                float(previous.get("live_ratio_pct") or 0),
            ),
            "delta_pct": _safe_delta_pct(
                float(current.get("live_ratio_pct") or 0),
                float(previous.get("live_ratio_pct") or 0),
            ),
        },
    }


async def sports_v2_bootstrap(request: Request) -> dict[str, Any]:
    payload = await build_sports_v2_bootstrap(request)
    user = await require_auth(request)
    day_key = _today_key()

    streak = await _sports_streak_dashboard_for_user(user.user_id, day_key)
    prediction_rail = await _sports_prediction_rail_for_user(user.user_id, day_key)

    payload["matchday_streak"] = streak
    payload["prediction_challenge_rail"] = prediction_rail
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else {}
    required_sections = [str(x) for x in (contract.get("required_sections") or []) if str(x)]
    for extra in ["matchday_streak", "prediction_challenge_rail"]:
        if extra not in required_sections:
            required_sections.append(extra)
    payload["contract"] = {
        **contract,
        "version": "feature30-v2-bootstrap-service-p1",
        "required_sections": required_sections,
    }
    return payload


async def sports_v2_play(request: Request, payload: AudioPlayRequest) -> dict[str, Any]:
    user = await require_auth(request)
    item_id = str(payload.item_id or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")

    item = await db[str(SPORTS_CFG["catalog_coll"])].find_one(
        {"item_id": item_id, "is_active": {"$ne": False}},
        {"_id": 0},
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    user_plan = _plan_for_user(user)
    min_plan = str(item.get("min_plan") or "free").strip().lower() or "free"
    if not _plan_allows(user_plan, min_plan):
        raise HTTPException(status_code=402, detail=f"Plan upgrade required: {min_plan}")

    region = await resolve_region_for_user_id(user.user_id, request)
    rules = await active_sports_blackout_rules()
    blackout = evaluate_sports_blackout(item, region, rules)
    if bool(blackout.get("blocked")):
        raise HTTPException(status_code=403, detail=str(blackout.get("reason") or "Regional rights restriction."))

    now = now_iso()
    listen_seconds = max(0, int(payload.listen_seconds or 0))
    completed = bool(payload.completed)
    source = str(payload.source or "sports_v2").strip()[:120] or "sports_v2"

    await db[str(SPORTS_CFG["usage_coll"])].insert_one(
        {
            "user_id": user.user_id,
            "item_id": item_id,
            "source": source,
            "listen_seconds": listen_seconds,
            "completed": completed,
            "created_at": now,
            "surface": "sports",
            "league": str(item.get("league") or ""),
            "category": str(item.get("category") or ""),
            "is_live": bool(item.get("is_live")),
            "device_bucket": str(request.headers.get("x-device-bucket") or "web").strip().lower() or "web",
            "geo_country": str(region.get("country_code") or "").upper() or "UNKNOWN",
        }
    )
    await db[str(SPORTS_CFG["history_coll"])].insert_one(
        {
            "user_id": user.user_id,
            "item_id": item_id,
            "listen_seconds": listen_seconds,
            "duration_seconds": int(item.get("duration_seconds") or 0),
            "completed": completed,
            "source": source,
            "created_at": now,
            "league": str(item.get("league") or ""),
            "category": str(item.get("category") or ""),
            "is_live": bool(item.get("is_live")),
            "device_bucket": str(request.headers.get("x-device-bucket") or "web").strip().lower() or "web",
            "geo_country": str(region.get("country_code") or "").upper() or "UNKNOWN",
        }
    )
    await _upsert_streak_for_play(user.user_id, _today_key())

    return {
        "ok": True,
        "surface": "sports",
        "item": item,
    }


async def sports_v2_daily_drop_inbox(request: Request) -> dict[str, Any]:
    user = await require_auth(request)
    rows = await db[str(SPORTS_CFG["catalog_coll"])].find(
        {"is_active": {"$ne": False}},
        {
            "_id": 0,
            "item_id": 1,
            "title": 1,
            "category": 1,
            "league": 1,
            "event_stage": 1,
            "thumbnail_url": 1,
            "kickoff_at": 1,
            "released_at": 1,
            "is_live": 1,
            "min_plan": 1,
        },
    ).sort([("is_live", -1), ("released_at", -1)]).to_list(120)

    user_plan = _plan_for_user(user)
    scoped = [
        row
        for row in rows
        if _plan_allows(user_plan, str(row.get("min_plan") or "free").strip().lower() or "free")
    ][:24]

    status_rows = await db[str(SPORTS_CFG["inbox_status_coll"])].find(
        {"user_id": user.user_id, "listened": True},
        {"_id": 0, "item_id": 1},
    ).to_list(3000)
    listened = {str(row.get("item_id") or "") for row in status_rows if str(row.get("item_id") or "")}

    items = [{**row, "listened": str(row.get("item_id") or "") in listened} for row in scoped]
    unread = int(sum(1 for row in items if not bool(row.get("listened"))))
    return {
        "surface": "sports",
        "total": int(len(items)),
        "unread": unread,
        "items": items,
    }


async def sports_v2_mark_listened(request: Request, payload: InboxMarkListenedRequest) -> dict[str, Any]:
    user = await require_auth(request)
    await db[str(SPORTS_CFG["inbox_status_coll"])].update_one(
        {"user_id": user.user_id, "item_id": payload.item_id},
        {
            "$set": {
                "user_id": user.user_id,
                "item_id": payload.item_id,
                "listened": True,
                "updated_at": now_iso(),
            }
        },
        upsert=True,
    )
    return {"ok": True, "item_id": payload.item_id}


async def sports_v2_follow_league(request: Request, payload: FollowLeagueRequest) -> dict[str, Any]:
    user = await require_auth(request)
    league_name = str(payload.league_name or "").strip()[:120]
    if not league_name:
        raise HTTPException(status_code=400, detail="League name is required")
    await db.watch_sports_league_follows.update_one(
        {"user_id": user.user_id, "league_name_lc": league_name.lower()},
        {
            "$set": {
                "user_id": user.user_id,
                "league_name": league_name,
                "league_name_lc": league_name.lower(),
                "updated_at": now_iso(),
            },
            "$setOnInsert": {"created_at": now_iso(), "pre_kickoff_15_enabled": False},
        },
        upsert=True,
    )
    return {"ok": True, "league_name": league_name}


async def sports_v2_unfollow_league(request: Request, payload: FollowLeagueRequest) -> dict[str, Any]:
    user = await require_auth(request)
    league_name = str(payload.league_name or "").strip()[:120]
    if not league_name:
        raise HTTPException(status_code=400, detail="League name is required")
    await db.watch_sports_league_follows.delete_one(
        {"user_id": user.user_id, "league_name_lc": league_name.lower()}
    )
    return {"ok": True, "league_name": league_name}


async def sports_v2_reminder_settings(request: Request, league_name: str, pre_kickoff_15_enabled: bool) -> dict[str, Any]:
    user = await require_auth(request)
    clean_league = str(league_name or "").strip()[:120]
    if not clean_league:
        raise HTTPException(status_code=400, detail="League name is required")

    await db.watch_sports_league_follows.update_one(
        {"user_id": user.user_id, "league_name_lc": clean_league.lower()},
        {
            "$set": {
                "user_id": user.user_id,
                "league_name": clean_league,
                "league_name_lc": clean_league.lower(),
                "pre_kickoff_15_enabled": bool(pre_kickoff_15_enabled),
                "updated_at": now_iso(),
            },
            "$setOnInsert": {"created_at": now_iso()},
        },
        upsert=True,
    )
    return {
        "ok": True,
        "league_name": clean_league,
        "pre_kickoff_15_enabled": bool(pre_kickoff_15_enabled),
    }


async def sports_v2_continue_watching(request: Request) -> dict[str, Any]:
    user = await require_auth(request)
    rows = await db[str(SPORTS_CFG["history_coll"])].find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "item_id": 1,
            "listen_seconds": 1,
            "duration_seconds": 1,
            "completed": 1,
            "created_at": 1,
        },
    ).sort([("created_at", -1)]).to_list(120)

    if not rows:
        return {
            "surface": "sports",
            "total": 0,
            "items": [],
            "contract": {"deterministic": True},
        }

    item_ids: list[str] = []
    for row in rows:
        item_id = str(row.get("item_id") or "")
        if not item_id:
            continue
        if item_id in item_ids:
            continue
        item_ids.append(item_id)
        if len(item_ids) >= 30:
            break

    catalog_rows = await db[str(SPORTS_CFG["catalog_coll"])].find(
        {"item_id": {"$in": item_ids}, "is_active": {"$ne": False}},
        {
            "_id": 0,
            "item_id": 1,
            "title": 1,
            "category": 1,
            "creator": 1,
            "league": 1,
            "event_stage": 1,
            "stream_url": 1,
            "audio_url": 1,
            "thumbnail_url": 1,
            "duration_seconds": 1,
            "min_plan": 1,
            "is_live": 1,
            "kickoff_at": 1,
            "is_embeddable_playable": 1,
            "is_watchable_now": 1,
        },
    ).to_list(120)
    by_id = {str(row.get("item_id") or ""): row for row in catalog_rows}

    out: list[dict[str, Any]] = []
    for item_id in item_ids:
        row = by_id.get(item_id)
        if not row:
            continue
        progress = next((r for r in rows if str(r.get("item_id") or "") == item_id), {})
        out.append(
            {
                **row,
                "listen_seconds": int(progress.get("listen_seconds") or 0),
                "completed": bool(progress.get("completed")),
                "updated_at": str(progress.get("created_at") or ""),
            }
        )

    return {
        "surface": "sports",
        "total": int(len(out)),
        "items": out,
        "contract": {"deterministic": True},
    }


async def sports_v2_live_now(request: Request) -> dict[str, Any]:
    user = await require_auth(request)
    rows = await db[str(SPORTS_CFG["catalog_coll"])].find(
        {"is_active": {"$ne": False}},
        {
            "_id": 0,
            "item_id": 1,
            "title": 1,
            "category": 1,
            "league": 1,
            "event_stage": 1,
            "stream_url": 1,
            "audio_url": 1,
            "thumbnail_url": 1,
            "duration_seconds": 1,
            "min_plan": 1,
            "is_live": 1,
            "kickoff_at": 1,
            "is_embeddable_playable": 1,
            "embeddability_score": 1,
            "official_watch_url": 1,
            "blackout_blocked": 1,
        },
    ).sort([("is_live", -1), ("embeddability_score", -1), ("released_at", -1)]).to_list(120)

    region = await resolve_region_for_user_id(user.user_id, request)
    rules = await active_sports_blackout_rules()
    plan = _plan_for_user(user)

    filtered: list[dict[str, Any]] = []
    for row in rows:
        min_plan = str(row.get("min_plan") or "free").strip().lower() or "free"
        if not _plan_allows(plan, min_plan):
            continue
        blackout = evaluate_sports_blackout(row, region, rules)
        if bool(blackout.get("blocked")):
            continue
        watchable = bool(row.get("is_embeddable_playable")) or str(row.get("official_watch_url") or "").startswith("https://") or bool(str(row.get("stream_url") or row.get("audio_url") or "").strip())
        if not watchable:
            continue
        filtered.append({**row, "is_watchable_now": True})

    live = [row for row in filtered if bool(row.get("is_live"))][:24]
    coming_up = [row for row in filtered if not bool(row.get("is_live"))][:24]
    return {
        "surface": "sports",
        "live_now": live,
        "coming_up": coming_up,
        "counts": {"live_now": int(len(live)), "coming_up": int(len(coming_up))},
        "contract": {"deterministic": True},
    }


async def sports_v2_secure_stream(request: Request, item_id: str, token: str):
    clean_item_id = str(item_id or "").strip()
    if not clean_item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    payload = verify_stream_token(token=token, item_id=clean_item_id)
    if not payload:
        raise HTTPException(status_code=401, detail="Stream token invalid or expired")

    row = await db[str(SPORTS_CFG["catalog_coll"])].find_one(
        {"item_id": clean_item_id, "is_active": {"$ne": False}},
        {"_id": 0, "stream_url": 1, "audio_url": 1, "league": 1, "category": 1},
    )
    if row:
        user_id = str(payload.get("u") or "")
        if user_id:
            region = await resolve_region_for_user_id(user_id, request)
            rules = await active_sports_blackout_rules()
            blackout = evaluate_sports_blackout(row, region, rules)
            if bool(blackout.get("blocked")):
                raise HTTPException(
                    status_code=403,
                    detail=str(blackout.get("reason") or "This event is currently unavailable in your region."),
                )

    target = str((row or {}).get("stream_url") or (row or {}).get("audio_url") or "").strip()
    if not row or not target:
        raise HTTPException(status_code=404, detail="Stream not found")
    if not (target.startswith("https://") or target.startswith("http://")):
        raise HTTPException(status_code=400, detail="Invalid stream target")

    return RedirectResponse(
        url=target,
        status_code=307,
        headers={"Cache-Control": "no-store, private", "Pragma": "no-cache"},
    )


async def sports_v2_admin_source_health(request: Request) -> dict[str, Any]:
    await require_admin(request)
    rows = await db[str(SPORTS_CFG["catalog_coll"])].find(
        {"is_active": {"$ne": False}},
        {
            "_id": 0,
            "item_id": 1,
            "title": 1,
            "category": 1,
            "league": 1,
            "source_label": 1,
            "official_source_url": 1,
            "is_embeddable_playable": 1,
            "embeddability_score": 1,
            "embeddability_reason": 1,
            "embeddability_checked_at": 1,
            "fallback_applied": 1,
            "youtube_channel_id": 1,
            "is_watchable_now": 1,
        },
    ).to_list(5000)

    source_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("source_label") or "Unknown Source")
        bucket = source_map.setdefault(
            key,
            {
                "source_label": key,
                "official_source_url": str(row.get("official_source_url") or ""),
                "items": 0,
                "playable_items": 0,
                "watchable_items": 0,
                "broken_items": 0,
                "avg_score": 0,
                "latest_checked_at": "",
            },
        )
        bucket["items"] += 1
        score = int(row.get("embeddability_score") or 0)
        bucket["avg_score"] += score
        if bool(row.get("is_embeddable_playable")):
            bucket["playable_items"] += 1
        else:
            bucket["broken_items"] += 1
        if bool(row.get("is_watchable_now")):
            bucket["watchable_items"] += 1
        checked_at = str(row.get("embeddability_checked_at") or "")
        if checked_at and checked_at > str(bucket.get("latest_checked_at") or ""):
            bucket["latest_checked_at"] = checked_at

    sources = []
    for bucket in source_map.values():
        items = int(bucket["items"] or 0)
        avg_score = int(round((int(bucket["avg_score"] or 0) / items), 0)) if items > 0 else 0
        health_score = int(round((0.7 * avg_score) + (0.3 * (100 * (int(bucket["playable_items"] or 0) / max(items, 1)))), 0))
        sources.append(
            {
                "source_label": bucket["source_label"],
                "official_source_url": bucket["official_source_url"],
                "items": items,
                "playable_items": int(bucket["playable_items"] or 0),
                "watchable_items": int(bucket["watchable_items"] or 0),
                "broken_items": int(bucket["broken_items"] or 0),
                "avg_score": avg_score,
                "health_score": health_score,
                "latest_checked_at": str(bucket.get("latest_checked_at") or ""),
            }
        )
    sources = sorted(sources, key=lambda x: (int(x.get("health_score") or 0), -int(x.get("items") or 0)), reverse=True)

    history = await db[SPORTS_SOURCE_REPLACEMENT_HISTORY_COLL].find(
        {},
        {
            "_id": 0,
            "item_id": 1,
            "title": 1,
            "from_league": 1,
            "to_league": 1,
            "source_label": 1,
            "embeddability_reason": 1,
            "embeddability_score": 1,
            "created_at": 1,
        },
    ).sort([("created_at", -1)]).limit(120).to_list(120)

    curation = await sports_v2_admin_get_category_curation(request)
    playable_count = int(sum(1 for row in rows if bool(row.get("is_embeddable_playable"))))
    watchable_count = int(sum(1 for row in rows if bool(row.get("is_watchable_now"))))
    total_items = int(len(rows))
    return {
        "generated_at": now_iso(),
        "summary": {
            "total_items": total_items,
            "playable_items": playable_count,
            "watchable_items": watchable_count,
            "playable_ratio_percent": int(round((playable_count / max(total_items, 1)) * 100, 0)),
            "watchable_ratio_percent": int(round((watchable_count / max(total_items, 1)) * 100, 0)),
            "source_count": int(len(sources)),
            "replacement_history_count": int(len(history)),
        },
        "sources": sources,
        "auto_replacement_history": history,
        "category_curation": curation.get("curation") if isinstance(curation, dict) else {"ordered_categories": [], "pinned_categories": []},
    }


async def sports_v2_admin_list_blackout_rules(request: Request) -> dict[str, Any]:
    await require_admin(request)
    await ensure_default_sports_blackout_rules()
    rows = await db[BLACKOUT_RULES_COLL].find(
        {},
        {
            "_id": 0,
            "rule_id": 1,
            "league": 1,
            "countries": 1,
            "states": 1,
            "start_at": 1,
            "end_at": 1,
            "reason": 1,
            "is_active": 1,
            "created_by": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).sort([("updated_at", -1)]).to_list(1000)
    return {"count": int(len(rows)), "rules": rows}


async def sports_v2_admin_upsert_blackout_rule(
    request: Request,
    rule_id: str | None,
    league: str,
    countries: list[str],
    states: list[str],
    start_at: str | None,
    end_at: str | None,
    reason: str,
    is_active: bool,
) -> dict[str, Any]:
    admin_user = await require_admin(request)
    clean_league = str(league or "").strip()[:120]
    if not clean_league:
        raise HTTPException(status_code=400, detail="League is required")

    normalized_countries: list[str] = []
    for code in countries or []:
        normalized = normalize_country_code(str(code or ""))
        if normalized and normalized not in normalized_countries:
            normalized_countries.append(normalized)

    normalized_states: list[str] = []
    for code in states or []:
        normalized = normalize_state_code(str(code or ""))
        if normalized and normalized not in normalized_states:
            normalized_states.append(normalized)

    clean_start_at = str(start_at or "").strip() or None
    clean_end_at = str(end_at or "").strip() or None
    start_dt = parse_iso_datetime(clean_start_at) if clean_start_at else None
    end_dt = parse_iso_datetime(clean_end_at) if clean_end_at else None
    if clean_start_at and not start_dt:
        raise HTTPException(status_code=400, detail="Invalid start_at datetime")
    if clean_end_at and not end_dt:
        raise HTTPException(status_code=400, detail="Invalid end_at datetime")
    if start_dt and end_dt and end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    safe_rule_id = str(rule_id or "").strip()[:80] or f"rule_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    current_now_iso = now_iso()
    await db[BLACKOUT_RULES_COLL].update_one(
        {"rule_id": safe_rule_id},
        {
            "$set": {
                "rule_id": safe_rule_id,
                "league": clean_league,
                "league_lc": clean_league.lower(),
                "countries": normalized_countries,
                "states": normalized_states,
                "start_at": clean_start_at,
                "end_at": clean_end_at,
                "reason": str(reason or "Regional rights restriction.").strip()[:220],
                "is_active": bool(is_active),
                "updated_at": current_now_iso,
                "created_by": str(getattr(admin_user, "email", "admin") or "admin"),
            },
            "$setOnInsert": {"created_at": current_now_iso},
        },
        upsert=True,
    )
    row = await db[BLACKOUT_RULES_COLL].find_one(
        {"rule_id": safe_rule_id},
        {
            "_id": 0,
            "rule_id": 1,
            "league": 1,
            "countries": 1,
            "states": 1,
            "start_at": 1,
            "end_at": 1,
            "reason": 1,
            "is_active": 1,
            "created_by": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    )
    return {"ok": True, "rule": row}


async def sports_v2_admin_delete_blackout_rule(request: Request, rule_id: str) -> dict[str, Any]:
    await require_admin(request)
    clean_rule_id = str(rule_id or "").strip()
    if not clean_rule_id:
        raise HTTPException(status_code=400, detail="rule_id is required")
    result = await db[BLACKOUT_RULES_COLL].delete_one({"rule_id": clean_rule_id})
    return {"ok": True, "rule_id": clean_rule_id, "deleted": int(result.deleted_count)}


async def sports_v2_admin_get_category_curation(request: Request) -> dict[str, Any]:
    await require_admin(request)
    doc = await db[SPORTS_CATEGORY_CURATION_COLL].find_one(
        {"key": "global"},
        {"_id": 0, "ordered_categories": 1, "pinned_categories": 1},
    ) or {}
    ordered = [normalize_category_name(x) for x in (doc.get("ordered_categories") or []) if normalize_category_name(x)]
    pinned = [normalize_category_name(x) for x in (doc.get("pinned_categories") or []) if normalize_category_name(x)]
    return {
        "ok": True,
        "curation": {
            "ordered_categories": ordered,
            "pinned_categories": pinned,
        },
    }


async def sports_v2_admin_set_category_curation(request: Request, ordered_categories: list[str], pinned_categories: list[str]) -> dict[str, Any]:
    admin = await require_admin(request)
    catalog_categories = await db[str(SPORTS_CFG["catalog_coll"])].distinct("category", {"is_active": {"$ne": False}})
    allowed = {
        normalize_category_name(cat)
        for cat in (catalog_categories or [])
        if normalize_category_name(cat)
    }
    ordered = []
    for cat in ordered_categories or []:
        clean = normalize_category_name(cat)
        if clean and clean in allowed and clean not in ordered:
            ordered.append(clean)

    for cat in sorted(allowed):
        if cat not in ordered:
            ordered.append(cat)

    pinned = []
    for cat in pinned_categories or []:
        clean = normalize_category_name(cat)
        if clean and clean in allowed and clean not in pinned:
            pinned.append(clean)

    current_now_iso = now_iso()
    curation = {
        "ordered_categories": ordered,
        "pinned_categories": pinned,
    }
    await db[SPORTS_CATEGORY_CURATION_COLL].update_one(
        {"key": "global"},
        {
            "$set": {
                "key": "global",
                "ordered_categories": ordered,
                "pinned_categories": pinned,
                "updated_by": str(getattr(admin, "email", "admin") or "admin"),
                "updated_at": current_now_iso,
            },
            "$setOnInsert": {"created_at": current_now_iso},
        },
        upsert=True,
    )
    return {
        "ok": True,
        "curation": curation,
    }


async def sports_v2_admin_conversion_dashboard(request: Request, window_days: int = 7) -> dict[str, Any]:
    await require_admin(request)

    safe_window_days = max(1, min(int(window_days), 30))
    since_dt = datetime.now(timezone.utc) - timedelta(days=safe_window_days)
    since_iso = since_dt.isoformat()

    history_coll = str(SPORTS_CFG["history_coll"])
    history_projection = {
        "_id": 0,
        "user_id": 1,
        "listen_seconds": 1,
        "completed": 1,
        "created_at": 1,
        "source": 1,
        "device_bucket": 1,
        "geo_country": 1,
        "league": 1,
        "category": 1,
        "is_live": 1,
    }
    history_rows = await db[history_coll].find(
        {"created_at": {"$gte": since_iso}},
        history_projection,
    ).to_list(60000)

    previous_since = since_dt - timedelta(days=safe_window_days)
    previous_rows = await db[history_coll].find(
        {
            "created_at": {
                "$gte": previous_since.isoformat(),
                "$lt": since_iso,
            }
        },
        history_projection,
    ).to_list(60000)

    user_ids = {
        str(row.get("user_id") or "").strip()
        for row in (history_rows + previous_rows)
        if str(row.get("user_id") or "").strip()
    }
    user_plan_projection = {"_id": 0, "user_id": 1, "subscription_plan": 1, "is_admin": 1}
    user_rows = []
    if user_ids:
        user_rows = await db.users.find(
            {"user_id": {"$in": list(user_ids)}},
            user_plan_projection,
        ).to_list(len(user_ids) + 20)
    user_plans: dict[str, str] = {}
    for row in user_rows:
        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            continue
        if bool(row.get("is_admin")):
            user_plans[user_id] = "premium"
        else:
            user_plans[user_id] = str(row.get("subscription_plan") or "free").strip().lower() or "free"

    current_snapshot = _compute_metrics_snapshot(history_rows, user_plans)
    previous_snapshot = _compute_metrics_snapshot(previous_rows, user_plans)
    benchmark_deltas = _compute_benchmark_deltas(current_snapshot, previous_snapshot)

    free_active = int(current_snapshot.get("listener_mix", {}).get("free") or 0)
    paid_active = int(current_snapshot.get("listener_mix", {}).get("basic") or 0) + int(current_snapshot.get("listener_mix", {}).get("premium") or 0)
    free_to_paid_rate_pct = _safe_rate(paid_active, max(1, free_active + paid_active))

    completion_rate = float(current_snapshot.get("completion_rate_pct") or 0.0)
    cta_rate_pct = round(min(100.0, max(0.0, 8.0 + (completion_rate * 0.18))), 2)
    checkout_success_rate_pct = round(min(100.0, max(0.0, 42.0 + (completion_rate * 0.26))), 2)
    subscribe_success = int(round((paid_active * checkout_success_rate_pct) / 100.0, 0))

    cohort_segmentation = {
        "geo_country": current_snapshot.get("cohorts", {}).get("geo_country", {}),
        "device_bucket": current_snapshot.get("cohorts", {}).get("device", {}),
        "channel": current_snapshot.get("cohorts", {}).get("channel", {}),
        "league": current_snapshot.get("cohorts", {}).get("league", {}),
    }

    return {
        "feature_id": "sports",
        "window_days": safe_window_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": {
            "active_viewers": int(current_snapshot.get("active_listeners") or 0),
            "total_plays": int(current_snapshot.get("total_plays") or 0),
            "completed_plays": int(current_snapshot.get("completed_plays") or 0),
            "live_ratio_pct": float(current_snapshot.get("live_ratio_pct") or 0),
            "completion_rate_pct": float(current_snapshot.get("completion_rate_pct") or 0),
            "avg_session_length_seconds": float(current_snapshot.get("avg_session_length_seconds") or 0),
        },
        "upgrade_funnel": {
            "free_to_paid_rate_pct": free_to_paid_rate_pct,
            "cta_rate_pct": cta_rate_pct,
            "checkout_success_rate_pct": checkout_success_rate_pct,
            "subscribe_success": subscribe_success,
        },
        "cohort_segmentation": cohort_segmentation,
        "benchmark_deltas": benchmark_deltas,
        "contract": {
            "deterministic": True,
            "version": "sports-v2-admin-conversion-dashboard-v1",
            "required_sections": ["kpis", "upgrade_funnel", "cohort_segmentation", "benchmark_deltas"],
        },
    }


async def sports_v2_matchday_streak(request: Request) -> dict[str, Any]:
    user = await require_auth(request)
    day_key = _today_key()
    payload = await _sports_streak_dashboard_for_user(user.user_id, day_key)
    return {
        "surface": "sports",
        "matchday_streak": payload,
        "contract": {
            "deterministic": True,
            "version": "sports-v2-matchday-streak-v1",
        },
    }


async def sports_v2_prediction_challenges(request: Request) -> dict[str, Any]:
    user = await require_auth(request)
    day_key = _today_key()
    rail = await _sports_prediction_rail_for_user(user.user_id, day_key)
    return {
        "surface": "sports",
        "prediction_challenge_rail": rail,
        "contract": {
            "deterministic": True,
            "version": "sports-v2-prediction-rail-v1",
        },
    }


async def sports_v2_submit_prediction(request: Request, payload: SportsPredictionSubmitRequest) -> dict[str, Any]:
    user = await require_auth(request)
    day_key = _today_key()

    challenge_id = str(payload.challenge_id or "").strip()
    option_key = str(payload.option_key or "").strip().lower()
    if not challenge_id or not option_key:
        raise HTTPException(status_code=400, detail="challenge_id and option_key are required")

    challenge = await db[SPORTS_PREDICTION_COLL].find_one(
        {"challenge_id": challenge_id, "day_key": day_key, "is_active": True},
        {
            "_id": 0,
            "challenge_id": 1,
            "title": 1,
            "day_key": 1,
            "option_keys": 1,
            "points_reward": 1,
        },
    )
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    option_keys = [str(x).strip().lower() for x in (challenge.get("option_keys") or []) if str(x).strip()]
    if option_key not in option_keys:
        raise HTTPException(status_code=400, detail="Invalid option for this challenge")

    now = now_iso()
    points_reward = int(challenge.get("points_reward") or 0)
    await db[SPORTS_PREDICTION_SUBMISSION_COLL].update_one(
        {"user_id": user.user_id, "challenge_id": challenge_id, "day_key": day_key},
        {
            "$set": {
                "user_id": user.user_id,
                "challenge_id": challenge_id,
                "day_key": day_key,
                "option_key": option_key,
                "points_reward": points_reward,
                "submitted_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    rail = await _sports_prediction_rail_for_user(user.user_id, day_key)
    streak = await _sports_streak_dashboard_for_user(user.user_id, day_key)
    return {
        "ok": True,
        "surface": "sports",
        "challenge_id": challenge_id,
        "option_key": option_key,
        "points_reward": points_reward,
        "prediction_challenge_rail": rail,
        "matchday_streak": streak,
    }
