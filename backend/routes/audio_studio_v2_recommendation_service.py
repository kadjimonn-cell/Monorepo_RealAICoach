from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from zoneinfo import ZoneInfo

from emergentintegrations.llm.chat import LlmChat, UserMessage

from .db import EMERGENT_LLM_KEY, User, db


BEHAVIORAL_AI_CACHE_HOURS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _safe_timezone_name(name: str | None) -> str:
    candidate = str(name or "").strip()
    if not candidate:
        return "UTC"
    try:
        ZoneInfo(candidate)
        return candidate
    except Exception:
        return "UTC"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_llm_json(raw_text: str) -> dict[str, Any]:
    clean = str(raw_text or "").strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    try:
        return json.loads(clean)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}


def _taste_profile_collection_name(surface: str) -> str:
    return f"watch_{surface}_taste_profiles"


def _behavioral_ai_collection_name(surface: str) -> str:
    return f"watch_{surface}_behavioral_ai"


async def refresh_taste_profile(surface: str, user: User, *, history_coll: str) -> dict[str, Any]:
    history_rows = await db[str(history_coll)].find(
        {"user_id": user.user_id},
        {"_id": 0, "category": 1, "listen_seconds": 1, "completed": 1, "duration_seconds": 1, "created_at": 1},
    ).sort([("created_at", -1)]).to_list(400)

    if not history_rows:
        profile = {
            "user_id": user.user_id,
            "preferred_categories": [],
            "skip_intent_by_category": {},
            "completion_rate": 0.0,
            "updated_at": _now_iso(),
        }
        await db[_taste_profile_collection_name(surface)].update_one(
            {"user_id": user.user_id},
            {"$set": profile, "$setOnInsert": {"created_at": _now_iso()}},
            upsert=True,
        )
        return profile

    category_stats: dict[str, dict[str, float]] = {}
    completed_count = 0
    for row in history_rows:
        category = str(row.get("category") or "General")
        listen_seconds = float(row.get("listen_seconds") or 0)
        duration_seconds = float(row.get("duration_seconds") or 0)
        completed = bool(row.get("completed"))
        if completed:
            completed_count += 1

        threshold = max(30.0, duration_seconds * 0.15)
        skip_flag = 1.0 if (not completed and listen_seconds < threshold) else 0.0

        bucket = category_stats.setdefault(category, {"plays": 0.0, "completion": 0.0, "skips": 0.0})
        bucket["plays"] += 1.0
        bucket["completion"] += 1.0 if completed else 0.0
        bucket["skips"] += skip_flag

    ranked_categories = sorted(
        category_stats.items(),
        key=lambda kv: (kv[1]["completion"] * 2.0 + kv[1]["plays"] - kv[1]["skips"] * 2.5),
        reverse=True,
    )
    preferred_categories = [cat for cat, _ in ranked_categories[:6]]
    skip_intent_by_category = {
        cat: round((stats["skips"] / max(1.0, stats["plays"])), 4)
        for cat, stats in category_stats.items()
    }
    profile = {
        "user_id": user.user_id,
        "preferred_categories": preferred_categories,
        "skip_intent_by_category": skip_intent_by_category,
        "completion_rate": round(completed_count / max(1, len(history_rows)), 4),
        "updated_at": _now_iso(),
    }
    await db[_taste_profile_collection_name(surface)].update_one(
        {"user_id": user.user_id},
        {"$set": profile, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )
    return profile


async def compute_habit_window(surface: str, user: User, timezone_name: str, *, history_coll: str) -> dict[str, Any]:
    tz = ZoneInfo(_safe_timezone_name(timezone_name))
    rows = await db[str(history_coll)].find(
        {"user_id": user.user_id},
        {"_id": 0, "created_at": 1},
    ).sort([("created_at", -1)]).to_list(500)

    if not rows:
        return {
            "timezone": str(tz),
            "best_hour": 20,
            "label": "8:00 PM",
            "window": "evening",
            "confidence": 0.25,
        }

    hour_counts = [0] * 24
    for row in rows:
        dt = _parse_iso_datetime(str(row.get("created_at") or ""))
        if not dt:
            continue
        local_dt = dt.astimezone(tz)
        hour_counts[int(local_dt.hour)] += 1

    best_hour = max(range(24), key=lambda h: hour_counts[h])
    total = max(1, sum(hour_counts))
    confidence = hour_counts[best_hour] / total
    suffix = "AM" if best_hour < 12 else "PM"
    hour12 = best_hour % 12 or 12
    label = f"{hour12}:00 {suffix}"
    if 5 <= best_hour < 12:
        window = "morning"
    elif 12 <= best_hour < 17:
        window = "afternoon"
    elif 17 <= best_hour < 22:
        window = "evening"
    else:
        window = "night"

    return {
        "timezone": str(tz),
        "best_hour": int(best_hour),
        "label": label,
        "window": window,
        "confidence": round(confidence, 4),
    }


def advanced_ml_rank(
    visible_rows: list[dict[str, Any]],
    *,
    profile: dict[str, Any],
    habit_window: dict[str, Any],
) -> list[dict[str, Any]]:
    preferred = list(profile.get("preferred_categories") or [])
    skip_map = profile.get("skip_intent_by_category") or {}
    best_hour = int(habit_window.get("best_hour") or 20)

    def _score(item: dict[str, Any]) -> float:
        category = str(item.get("category") or "General")
        recency_bonus = 0.0
        released = _parse_iso_datetime(str(item.get("released_at") or ""))
        if released:
            hours_old = max(1.0, (_now() - released).total_seconds() / 3600.0)
            recency_bonus = max(0.0, 4.0 - min(4.0, hours_old / 24.0))

        preference_bonus = 0.0
        if category in preferred:
            preference_bonus = float((len(preferred) - preferred.index(category)) * 2.2)

        skip_penalty = float(skip_map.get(category) or 0.0) * 4.0
        hour_alignment = 0.5 if 18 <= best_hour <= 23 else 0.2
        premium_bonus = 0.7 if str(item.get("min_plan") or "free") == "premium" else 0.1

        return recency_bonus + preference_bonus + hour_alignment + premium_bonus - skip_penalty

    return sorted(visible_rows, key=_score, reverse=True)


async def adaptive_queue(surface: str, user: User, visible_rows: list[dict[str, Any]], *, history_coll: str) -> list[dict[str, Any]]:
    profile = await refresh_taste_profile(surface, user, history_coll=history_coll)
    preferred = list(profile.get("preferred_categories") or [])
    skip_map = profile.get("skip_intent_by_category") or {}

    def _rank(item: dict[str, Any]) -> float:
        cat = str(item.get("category") or "General")
        pref_bonus = (len(preferred) - preferred.index(cat)) * 2.0 if cat in preferred else 0.0
        skip_penalty = float(skip_map.get(cat) or 0.0) * 3.0
        premium_bonus = 0.5 if str(item.get("min_plan") or "free") == "premium" else 0.0
        return pref_bonus + premium_bonus - skip_penalty

    ranked = sorted(visible_rows, key=_rank, reverse=True)
    explained: list[dict[str, Any]] = []
    for item in ranked[:18]:
        category = str(item.get("category") or "General")
        skip_intent = float(skip_map.get(category) or 0.0)
        if category in preferred[:3]:
            reason = f"Top category match: {category}"
        elif skip_intent <= 0.15:
            reason = f"Low-skip behavior in {category}"
        else:
            reason = "Fresh pick aligned with your listening pattern"
        explained.append({**item, "why_recommended": reason})
    return explained


def fallback_behavioral_ai(visible_rows: list[dict[str, Any]], preferred_categories: list[str]) -> dict[str, Any]:
    follow_up_ids = [str(row.get("item_id") or "") for row in visible_rows[:8] if str(row.get("item_id") or "")]
    rail_title = "Continue your top categories" if preferred_categories else "Keep your momentum"
    return {
        "source": "deterministic",
        "reengagement_nudge": "You are one tap away from your next high-focus session.",
        "follow_up_item_ids": follow_up_ids[:8],
        "dynamic_rails": [{"title": rail_title, "item_ids": follow_up_ids[:10]}],
        "best_time_to_return": {"timezone": "UTC", "label": "8:00 PM", "window": "evening", "confidence": 0.25},
    }


async def build_behavioral_ai(
    surface: str,
    user: User,
    visible_rows: list[dict[str, Any]],
    *,
    timezone_name: str,
    history_coll: str,
    ml_enabled: bool,
) -> dict[str, Any]:
    profile = await refresh_taste_profile(surface, user, history_coll=history_coll)
    preferred_categories = list(profile.get("preferred_categories") or [])
    habit_window = await compute_habit_window(surface, user, timezone_name, history_coll=history_coll)
    fallback = fallback_behavioral_ai(visible_rows, preferred_categories)
    fallback["best_time_to_return"] = habit_window
    if not visible_rows:
        return fallback

    candidate_rows = advanced_ml_rank(visible_rows, profile=profile, habit_window=habit_window) if ml_enabled else list(visible_rows)

    coll = db[_behavioral_ai_collection_name(surface)]
    cached = await coll.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    cached_snapshot = cached.get("snapshot") if isinstance(cached.get("snapshot"), dict) else {}
    cached_dt = _parse_iso_datetime(str(cached.get("updated_at") or ""))
    if (
        cached_dt
        and (_now() - cached_dt).total_seconds() <= BEHAVIORAL_AI_CACHE_HOURS * 3600
        and cached_snapshot
        and isinstance(cached_snapshot.get("best_time_to_return"), dict)
    ):
        return cached_snapshot

    if not EMERGENT_LLM_KEY:
        return fallback

    candidates = [
        {
            "item_id": str(row.get("item_id") or ""),
            "title": str(row.get("title") or ""),
            "category": str(row.get("category") or ""),
            "creator": str(row.get("creator") or ""),
        }
        for row in candidate_rows[:36]
        if str(row.get("item_id") or "")
    ]
    if not candidates:
        return fallback

    prompt = (
        "Return strict JSON only with keys: reengagement_nudge, follow_up_item_ids, dynamic_rails. "
        "reengagement_nudge <= 120 chars. "
        "follow_up_item_ids must use only provided candidate item_ids (max 8). "
        "dynamic_rails is an array (max 3) of {title, item_ids} using only candidate item_ids. "
        f"Preferred categories: {preferred_categories}. Habit window: {habit_window}. Candidates: {candidates}."
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"wah-behavior-{surface}-{user.user_id}-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You are a retention strategist for media apps. "
                "Generate concise addictive-but-safe follow-up sequencing. Return JSON only."
            ),
        ).with_model("openai", "gpt-5.2")
        response = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=8.0)
        raw = response.text if hasattr(response, "text") else str(response)
        parsed = _parse_llm_json(str(raw or ""))

        allowed_ids = {str(item.get("item_id") or "") for item in candidates}
        follow_up_item_ids = [
            item_id
            for item_id in [str(x or "").strip() for x in (parsed.get("follow_up_item_ids") or [])]
            if item_id in allowed_ids
        ][:8]

        dynamic_rails: list[dict[str, Any]] = []
        for rail in (parsed.get("dynamic_rails") or [])[:3]:
            if not isinstance(rail, dict):
                continue
            title = str(rail.get("title") or "").strip()[:72]
            item_ids = [
                item_id
                for item_id in [str(x or "").strip() for x in (rail.get("item_ids") or [])]
                if item_id in allowed_ids
            ][:10]
            if title and item_ids:
                dynamic_rails.append({"title": title, "item_ids": item_ids})

        snapshot = {
            "source": "ml+llm:gpt-5.2" if ml_enabled else "llm:gpt-5.2",
            "reengagement_nudge": str(parsed.get("reengagement_nudge") or "").strip()[:120]
            or fallback["reengagement_nudge"],
            "follow_up_item_ids": follow_up_item_ids or fallback["follow_up_item_ids"],
            "dynamic_rails": dynamic_rails or fallback["dynamic_rails"],
            "best_time_to_return": habit_window,
        }
        await coll.update_one(
            {"user_id": user.user_id},
            {
                "$set": {
                    "user_id": user.user_id,
                    "surface": surface,
                    "snapshot": snapshot,
                    "updated_at": _now_iso(),
                },
                "$setOnInsert": {"created_at": _now_iso()},
            },
            upsert=True,
        )
        return snapshot
    except Exception:
        fallback["source"] = "ml+deterministic" if ml_enabled else "deterministic"
        return fallback
