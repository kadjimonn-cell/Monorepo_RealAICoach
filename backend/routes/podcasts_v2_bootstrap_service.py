from __future__ import annotations

from typing import Any

from fastapi import Request

from .db import User, db, require_auth
from .podcasts_v2_recommendation_service import adaptive_queue, build_behavioral_ai
from .watch_audio_shared import (
    SURFACE_CONFIG,
    _daily_drop_inbox,
    _extract_timezone,
    _is_ml_pipeline_enabled,
    _materialize_items_by_ids,
    _period_key,
    _resolve_surface,
    _run_surface_daily_drop,
    _surface_quota_snapshot,
)


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
        "audio_url": 1,
        "stream_url": 1,
        "thumbnail_url": 1,
        "duration_seconds": 1,
        "min_plan": 1,
        "source_label": 1,
        "released_at": 1,
        "created_at": 1,
        "drop_key": 1,
        "drop_order": 1,
    }


def _safe_episode_number(value: Any) -> int:
    raw = str(value or "").strip().lower()
    if raw.startswith("episode "):
        raw = raw.replace("episode ", "", 1)
    if raw.startswith("ep "):
        raw = raw.replace("ep ", "", 1)
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return 0
    try:
        return int(digits)
    except Exception:
        return 0


def _build_story_arc(rows: list[dict[str, Any]], selected_item_id: str) -> dict[str, Any]:
    if not rows:
        return {"series_name": "", "items": []}

    selected = next((row for row in rows if str(row.get("item_id") or "") == selected_item_id), None)
    if not selected:
        selected = rows[0]

    target_series = str(selected.get("series_name") or "").strip()
    if not target_series:
        return {"series_name": "", "items": []}

    series_rows = [
        row
        for row in rows
        if str(row.get("series_name") or "").strip().lower() == target_series.lower()
    ]
    series_rows = sorted(
        series_rows,
        key=lambda row: (
            _safe_episode_number(str(row.get("title") or "")),
            str(row.get("released_at") or ""),
        ),
    )
    return {
        "series_name": target_series,
        "items": series_rows[:10],
    }


def _season_binge_rails(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("series_name") or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(row)

    rails: list[dict[str, Any]] = []
    for series_name, items in grouped.items():
        sorted_items = sorted(
            items,
            key=lambda row: (
                _safe_episode_number(str(row.get("title") or "")),
                str(row.get("released_at") or ""),
            ),
        )
        if len(sorted_items) < 3:
            continue
        rails.append(
            {
                "title": f"Binge {series_name}",
                "series_name": series_name,
                "items": sorted_items[:8],
            }
        )
    rails = sorted(rails, key=lambda row: len(row.get("items") or []), reverse=True)
    return rails[:6]


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


async def build_podcasts_v2_bootstrap(request: Request) -> dict[str, Any]:
    surface = "podcasts"
    cfg = _resolve_surface(surface)
    user = await require_auth(request)
    timezone_name = _extract_timezone(request)

    daily_drop = await _run_surface_daily_drop(surface, triggered_by="bootstrap:podcasts_v2")

    visible_rows = await _fetch_visible_rows_for_user(surface, user)
    featured_item = visible_rows[0] if visible_rows else None

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

    row_map = {
        str(row.get("item_id") or ""): row
        for row in visible_rows
        if str(row.get("item_id") or "")
    }
    smart_follow_up_items = _materialize_items_by_ids(
        [str(x or "") for x in (behavioral_ai.get("follow_up_item_ids") or [])],
        row_map,
        limit=10,
    )

    behavioral_rails: list[dict[str, Any]] = []
    for rail in (behavioral_ai.get("dynamic_rails") or [])[:3]:
        if not isinstance(rail, dict):
            continue
        title = str(rail.get("title") or "").strip()[:72]
        rail_items = _materialize_items_by_ids(
            [str(x or "") for x in (rail.get("item_ids") or [])],
            row_map,
            limit=10,
        )
        if title and rail_items:
            behavioral_rails.append({"title": title, "items": rail_items})

    selected_item_id = str((featured_item or {}).get("item_id") or "")
    podcast_story_arc = _build_story_arc(visible_rows, selected_item_id)
    season_binge_rails = _season_binge_rails(visible_rows)

    daily_drop_inbox = await _daily_drop_inbox(surface, user, limit=24)
    quota = await _surface_quota_snapshot(surface, user)
    categories = sorted({str(row.get("category") or "General") for row in visible_rows})

    return {
        "feature_id": "watch-videos-my-podcasts",
        "surface": surface,
        "label": cfg.get("label"),
        "route": "/features/my-podcasts",
        "timezone": timezone_name,
        "cadence": str(cfg.get("drop_cadence") or "daily").lower(),
        "period_key": _period_key(str(cfg.get("drop_cadence") or "daily").lower()),
        "quota": quota,
        "total_catalog": int(len(visible_rows)),
        "total_visible": int(len(visible_rows)),
        "categories": categories,
        "catalog": visible_rows,
        "featured_item": featured_item,
        "adaptive_next_queue": adaptive_next_queue,
        "behavioral_ai": behavioral_ai,
        "smart_follow_up_items": smart_follow_up_items,
        "behavioral_rails": behavioral_rails,
        "podcast_story_arc": podcast_story_arc,
        "season_binge_rails": season_binge_rails,
        "daily_drop_inbox": daily_drop_inbox,
        "daily_drop": daily_drop,
        "contract": {
            "version": "feature29-v2-bootstrap-service",
            "deterministic": True,
            "no_manual_input": True,
            "no_upload": True,
            "required_sections": [
                "quota",
                "catalog",
                "adaptive_next_queue",
                "behavioral_ai",
                "podcast_story_arc",
                "season_binge_rails",
                "daily_drop_inbox",
            ],
        },
    }
