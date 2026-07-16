from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Request

from .db import db, require_auth
from .sports_v2_internal import (
    SPORTS_STREAM_TOKEN_TTL_SECONDS,
    active_sports_blackout_rules,
    attach_blackout_metadata,
    build_secure_stream_path,
    followed_sports_leagues,
    issue_stream_token,
    now_iso,
    now_utc,
    resolve_user_region,
    sports_league_reminder_settings,
    evaluate_sports_blackout,
)


PLAN_LEVEL = {"free": 0, "basic": 1, "premium": 2}
PLAN_DAILY_PLAY_CAPS = {"free": 5, "basic": 120, "premium": -1}

SPORTS_CFG = {
    "feature_id": "watch-videos-sports",
    "catalog_coll": "watch_sports_catalog",
    "history_coll": "watch_sports_history",
    "behavioral_ai_coll": "watch_sports_behavioral_ai",
    "inbox_status_coll": "watch_sports_inbox_status",
}


def _plan_label(user: Any) -> str:
    if bool(getattr(user, "is_admin", False)):
        return "premium"
    return str(getattr(user, "subscription_plan", "free") or "free").strip().lower() or "free"


def _plan_allows(user_plan: str, min_plan: str) -> bool:
    return int(PLAN_LEVEL.get(str(user_plan or "free"), 0)) >= int(PLAN_LEVEL.get(str(min_plan or "free"), 0))


def _scope_label_for_plan(plan: str) -> str:
    if plan == "premium":
        return "All events"
    if plan == "basic":
        return "Core + selected premium previews"
    return "Free tier events"


def _prepare_sports_client_item(
    row: dict[str, Any],
    *,
    user_id: str,
    blackout: dict[str, Any],
) -> dict[str, Any]:
    item = attach_blackout_metadata(row, blackout)
    blocked = bool(item.get("blackout_blocked"))
    has_stream = bool(str(item.get("stream_url") or item.get("audio_url") or "").strip())
    embeddable = bool(item.get("is_embeddable_playable"))
    official_watch = str(item.get("official_watch_url") or "").strip().startswith("https://")
    watchable = (not blocked) and (embeddable or official_watch or has_stream)

    item["is_watchable_now"] = bool(watchable)
    item["watch_now_mode"] = "embedded" if embeddable else ("official" if official_watch else "none")

    if blocked:
        item["stream_url"] = ""
        item["audio_url"] = ""
        item["youtube_embed_url"] = ""
        item["stream_protection"] = "blackout_locked"
        item["stream_token_ttl_seconds"] = 0
        item["watch_now_mode"] = "none"
        return item

    if has_stream:
        exp = int((now_utc() + timedelta(seconds=SPORTS_STREAM_TOKEN_TTL_SECONDS)).timestamp())
        token = issue_stream_token(user_id=user_id, item_id=str(item.get("item_id") or ""), expires_at=exp)
        protected = build_secure_stream_path(item_id=str(item.get("item_id") or ""), token=token)
        item["stream_url"] = protected
        item["audio_url"] = protected
        item["stream_protection"] = "signed_url"
        item["stream_token_ttl_seconds"] = SPORTS_STREAM_TOKEN_TTL_SECONDS
    else:
        item["stream_protection"] = "none"
        item["stream_token_ttl_seconds"] = 0

    return item


async def build_sports_v2_bootstrap(request: Request) -> dict:
    user = await require_auth(request)
    user_plan = _plan_label(user)

    plays_used_today = await db[str(SPORTS_CFG["history_coll"])].count_documents(
        {
            "user_id": user.user_id,
            "created_at": {"$gte": now_utc().date().isoformat()},
        }
    )
    daily_cap = int(PLAN_DAILY_PLAY_CAPS.get(user_plan, 5))
    plays_remaining = -1 if daily_cap < 0 else max(0, daily_cap - int(plays_used_today))

    raw_rows = await db[str(SPORTS_CFG["catalog_coll"])].find(
        {"is_active": {"$ne": False}},
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
            "youtube_embed_url": 1,
            "official_watch_url": 1,
            "official_source_url": 1,
            "thumbnail_url": 1,
            "duration_seconds": 1,
            "released_at": 1,
            "kickoff_at": 1,
            "min_plan": 1,
            "is_live": 1,
            "is_embeddable_playable": 1,
            "embeddability_score": 1,
            "embeddability_reason": 1,
            "source_label": 1,
            "youtube_channel_id": 1,
        },
    ).sort([("is_live", -1), ("released_at", -1)]).to_list(1200)

    region = await resolve_user_region(user, request)
    rules = await active_sports_blackout_rules()

    catalog: list[dict[str, Any]] = []
    for row in raw_rows:
        min_plan = str(row.get("min_plan") or "free").strip().lower() or "free"
        if not _plan_allows(user_plan, min_plan):
            continue
        blackout = evaluate_sports_blackout(row, region, rules)
        catalog.append(_prepare_sports_client_item(row, user_id=user.user_id, blackout=blackout))

    categories = sorted({str(row.get("category") or "").strip() for row in catalog if str(row.get("category") or "").strip()})
    watchable_rows = [row for row in catalog if bool(row.get("is_watchable_now"))]
    live_watchable_rows = [row for row in watchable_rows if bool(row.get("is_live"))]
    featured_item = (live_watchable_rows[0] if live_watchable_rows else (watchable_rows[0] if watchable_rows else (catalog[0] if catalog else None)))

    status_rows = await db[str(SPORTS_CFG["inbox_status_coll"])].find(
        {"user_id": user.user_id, "listened": True},
        {"_id": 0, "item_id": 1},
    ).to_list(3000)
    listened = {str(row.get("item_id") or "") for row in status_rows if str(row.get("item_id") or "")}
    inbox_source = (live_watchable_rows + [row for row in watchable_rows if not bool(row.get("is_live"))])[:10]
    inbox_items = [{**row, "listened": (str(row.get("item_id") or "") in listened)} for row in inbox_source]
    unread = int(sum(1 for row in inbox_items if not bool(row.get("listened"))))

    follows = await followed_sports_leagues(user)
    reminders = await sports_league_reminder_settings(user)

    behavioral_row = await db[str(SPORTS_CFG["behavioral_ai_coll"])].find_one({}, {"_id": 0}) or {}
    behavioral_ai = {
        "best_time_to_return": behavioral_row.get("best_time_to_return") or {"label": "8:00 PM", "window": "evening"},
        "reengagement_nudge": str(behavioral_row.get("reengagement_nudge") or "Live action is peaking now — your best next event is queued."),
        "weekly_relevance_score": float(behavioral_row.get("weekly_relevance_score") or 0.72),
    }

    payload: dict[str, Any] = {
        "feature_id": str(SPORTS_CFG["feature_id"]),
        "label": "Sports",
        "surface": "sports",
        "route": "/features/sports",
        "quota": {
            "plan": user_plan,
            "daily_play_cap": daily_cap,
            "plays_used_today": int(plays_used_today),
            "plays_remaining_today": plays_remaining,
            "scope_label": _scope_label_for_plan(user_plan),
        },
        "categories": categories,
        "catalog": catalog,
        "featured_item": featured_item,
        "adaptive_next_queue": watchable_rows[:16],
        "behavioral_ai": behavioral_ai,
        "daily_drop_inbox": {
            "surface": "sports",
            "total": int(len(inbox_items)),
            "unread": unread,
            "items": inbox_items,
        },
        "followed_leagues": follows,
        "league_reminder_settings": reminders,
        "sports_playability_summary": {
            "total_count": int(len(catalog)),
            "playable_count": int(sum(1 for row in catalog if bool(row.get("is_embeddable_playable")))),
            "watchable_count": int(sum(1 for row in catalog if bool(row.get("is_watchable_now")))),
        },
        "playback_security": {
            "token_ttl_seconds": SPORTS_STREAM_TOKEN_TTL_SECONDS,
            "secure_stream_route": "/api/sports/v2/secure-stream",
        },
        "regional_access": {
            "country_code": str(region.get("country_code") or ""),
            "state_code": str(region.get("state_code") or ""),
            "active_blackout_rules": int(len(rules)),
        },
        "generated_at": now_iso(),
    }

    payload["contract"] = {
        "version": "feature30-v2-bootstrap-service",
        "deterministic": True,
        "no_manual_input": True,
        "no_upload": True,
        "required_sections": [
            "quota",
            "catalog",
            "adaptive_next_queue",
            "behavioral_ai",
            "daily_drop_inbox",
            "sports_playability_summary",
            "playback_security",
            "regional_access",
        ],
    }
    return payload
