from __future__ import annotations

from typing import Any

from fastapi import Request

from .audio_studio_v2_recommendation_service import adaptive_queue, build_behavioral_ai
from .db import User, db, require_auth
from .watch_audio_shared import (
    SURFACE_CONFIG,
    _audio_source_health_summary,
    _daily_drop_inbox,
    _extract_timezone,
    _followed_artist_releases,
    _followed_artists,
    _is_ml_pipeline_enabled,
    _materialize_items_by_ids,
    _period_key,
    _resolve_surface,
    _run_surface_daily_drop,
    _surface_quota_snapshot,
)


def _to_client_item(surface: str, row: dict[str, Any]) -> dict[str, Any]:
    """Simple client item converter for audio_studio surface (no request/user_id needed)"""
    return dict(row or {})


def _catalog_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "item_id": 1,
        "title": 1,
        "description": 1,
        "category": 1,
        "creator": 1,
        "content_kind": 1,
        "series_name": 1,
        "host_name": 1,
        "artist_name": 1,
        "album_name": 1,
        "audio_url": 1,
        "stream_url": 1,
        "playback_type": 1,
        "youtube_embed_url": 1,
        "youtube_channel_id": 1,
        "official_source_url": 1,
        "official_watch_url": 1,
        "is_embeddable_playable": 1,
        "embeddability_score": 1,
        "embeddability_reason": 1,
        "embeddability_checked_at": 1,
        "fallback_applied": 1,
        "fallback_from_league": 1,
        "is_watchable_now": 1,
        "watch_now_mode": 1,
        "thumbnail_url": 1,
        "duration_seconds": 1,
        "min_plan": 1,
        "source_label": 1,
        "source_trust_badge": 1,
        "league": 1,
        "event_stage": 1,
        "is_live": 1,
        "kickoff_at": 1,
        "tags": 1,
        "released_at": 1,
        "created_at": 1,
    }


async def _fetch_visible_rows_for_user(surface: str, user: User) -> list[dict[str, Any]]:
    cfg = _resolve_surface(surface)
    quota = await _surface_quota_snapshot(surface, user)
    plan = str(quota.get("plan") or "free").lower()
    plan_rank = {"free": 0, "basic": 1, "premium": 2}
    current_rank = plan_rank.get(plan, 0)

    rows = await db[str(cfg["catalog_coll"])].find(
        {"is_active": {"$ne": False}},
        _catalog_projection(),
    ).sort([("released_at", -1), ("created_at", -1)]).to_list(1200)

    visible_rows: list[dict[str, Any]] = []
    for row in rows:
        required_plan = str(row.get("min_plan") or "free").lower()
        required_rank = plan_rank.get(required_plan, 0)
        if required_rank > current_rank:
            continue
        visible_rows.append(row)

    return visible_rows


async def build_audio_studio_bootstrap(request: Request) -> dict[str, Any]:
    surface = "audio_studio"
    cfg = _resolve_surface(surface)
    user = await require_auth(request)
    timezone_name = _extract_timezone(request)

    # deterministic daily-drop execution and reporting
    daily_drop = await _run_surface_daily_drop(surface, triggered_by="bootstrap:audio_studio_v2")

    visible_rows = await _fetch_visible_rows_for_user(surface, user)
    items = [_to_client_item(surface, row) for row in visible_rows]
    featured_item = items[0] if items else None

    source_health = _audio_source_health_summary(visible_rows)

    ml_enabled = await _is_ml_pipeline_enabled()
    history_coll = str(SURFACE_CONFIG[surface]["history_coll"])

    adaptive_next_queue = await adaptive_queue(surface, user, visible_rows, history_coll=history_coll)
    behavioral_ai = await build_behavioral_ai(
        surface,
        user,
        visible_rows,
        timezone_name=timezone_name,
        history_coll=history_coll,
        ml_enabled=ml_enabled,
    )

    item_map = {str(row.get("item_id") or ""): _to_client_item(surface, row) for row in visible_rows if str(row.get("item_id") or "")}
    smart_follow_up_items = _materialize_items_by_ids(
        [str(x or "") for x in (behavioral_ai.get("follow_up_item_ids") or [])],
        item_map,
        limit=8,
    )

    dynamic_rails: list[dict[str, Any]] = []
    for rail in (behavioral_ai.get("dynamic_rails") or [])[:3]:
        if not isinstance(rail, dict):
            continue
        title = str(rail.get("title") or "").strip()[:72]
        item_ids = [str(x or "") for x in (rail.get("item_ids") or [])]
        rail_items = _materialize_items_by_ids(item_ids, item_map, limit=10)
        if title and rail_items:
            dynamic_rails.append({"title": title, "items": rail_items})

    followed_artists = await _followed_artists(user)
    followed_artist_new_releases = _followed_artist_releases(visible_rows, followed_artists)
    daily_drop_inbox = await _daily_drop_inbox(surface, user, limit=24)
    quota = await _surface_quota_snapshot(surface, user)

    categories = sorted({str(row.get("category") or "General") for row in visible_rows})
    return {
        "feature_id": cfg["feature_id"],
        "surface": surface,
        "route": cfg.get("route_hint"),
        "timezone": timezone_name,
        "cadence": str(cfg.get("drop_cadence") or "daily").lower(),
        "period_key": _period_key(str(cfg.get("drop_cadence") or "daily").lower()),
        "quota": quota,
        "catalog_count": int(len(items)),
        "categories": categories,
        "catalog": items,
        "featured_item": featured_item,
        "source_health": source_health,
        "adaptive_next_queue": adaptive_next_queue,
        "behavioral_ai": behavioral_ai,
        "smart_follow_up_items": smart_follow_up_items,
        "dynamic_rails": dynamic_rails,
        "followed_artists": followed_artists,
        "followed_artist_new_releases": followed_artist_new_releases,
        "daily_drop_inbox": daily_drop_inbox,
        "daily_drop": daily_drop,
        "contract": {
            "version": "feature28-v2-bootstrap-service",
            "deterministic": True,
            "required_sections": [
                "quota",
                "catalog",
                "source_health",
                "adaptive_next_queue",
                "behavioral_ai",
                "daily_drop_inbox",
            ],
        },
    }
