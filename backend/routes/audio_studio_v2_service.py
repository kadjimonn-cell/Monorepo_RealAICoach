from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from utils.access_control_engine import compute_effective_plan

from .db import db, require_admin, require_auth
from .watch_audio_shared import (
    AudioPlayRequest,
    FollowArtistRequest,
    InboxMarkListenedRequest,
    SURFACE_CONFIG,
    _daily_drop_inbox,
    _inbox_status_collection_name,
    _now_iso,
    _surface_play,
)
from .audio_studio_v2_bootstrap_service import build_audio_studio_bootstrap


def _safe_rate(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round((float(num) / float(den)) * 100.0, 2)


def _normalize_plan(plan: Any) -> str:
    value = str(plan or "free").strip().lower()
    if value in {"basic", "premium"}:
        return value
    return "free"


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
    total_listen_seconds = 0
    active_user_ids: set[str] = set()
    session_lengths: dict[str, int] = {}

    device_counts: dict[str, int] = {"web": 0, "native": 0, "unknown": 0}
    channel_counts: dict[str, int] = {}
    geo_counts: dict[str, int] = {}

    for row in history_rows:
        user_id = str(row.get("user_id") or "").strip()
        listen_seconds = int(row.get("listen_seconds") or 0)
        if listen_seconds < 0:
            listen_seconds = 0

        total_listen_seconds += listen_seconds
        if bool(row.get("completed")):
            completed_plays += 1

        device_bucket = str(row.get("device_bucket") or "unknown").strip().lower()
        if device_bucket not in {"web", "native"}:
            device_bucket = "unknown"
        device_counts[device_bucket] = int(device_counts.get(device_bucket) or 0) + 1

        channel = str(row.get("source") or "unknown").strip().lower() or "unknown"
        channel_counts[channel] = int(channel_counts.get(channel) or 0) + 1

        geo_country = _normalize_geo_country(row.get("geo_country"))
        geo_counts[geo_country] = int(geo_counts.get(geo_country) or 0) + 1

        if not user_id:
            continue

        active_user_ids.add(user_id)
        day_key = str(row.get("created_at") or "")[:10] or datetime.now(timezone.utc).date().isoformat()
        session_key = f"{user_id}:{day_key}"
        session_lengths[session_key] = int(session_lengths.get(session_key) or 0) + listen_seconds

    active_listeners = int(len(active_user_ids))
    avg_session_length_seconds = round(
        float(sum(session_lengths.values())) / float(max(len(session_lengths), 1)),
        2,
    )
    completion_rate_pct = _safe_rate(completed_plays, total_plays)

    free_engaged = 0
    basic_engaged = 0
    premium_engaged = 0
    for user_id in active_user_ids:
        plan = _normalize_plan(user_plans.get(user_id))
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
        "completion_rate_pct": completion_rate_pct,
        "avg_session_length_seconds": avg_session_length_seconds,
        "avg_listen_seconds_per_play": round(float(total_listen_seconds) / float(max(total_plays, 1)), 2),
        "listener_mix": {
            "free": int(free_engaged),
            "basic": int(basic_engaged),
            "premium": int(premium_engaged),
        },
        "cohorts": {
            "device": {k: int(v) for k, v in sorted(device_counts.items(), key=lambda kv: kv[1], reverse=True)},
            "channel": {k: int(v) for k, v in sorted(channel_counts.items(), key=lambda kv: kv[1], reverse=True)},
            "geo_country": {k: int(v) for k, v in sorted(geo_counts.items(), key=lambda kv: kv[1], reverse=True)},
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
    }


async def audio_studio_v2_bootstrap(request: Request) -> dict[str, Any]:
    return await build_audio_studio_bootstrap(request)


async def audio_studio_v2_play(request: Request, payload: AudioPlayRequest) -> dict[str, Any]:
    return await _surface_play("audio_studio", request, payload)


async def audio_studio_v2_follow_artist(request: Request, payload: FollowArtistRequest) -> dict[str, Any]:
    user = await require_auth(request)
    artist_name = str(payload.artist_name or "").strip()[:120]
    await db.watch_audio_artist_follows.update_one(
        {"user_id": user.user_id, "artist_name_lc": artist_name.lower()},
        {
            "$set": {
                "user_id": user.user_id,
                "artist_name": artist_name,
                "artist_name_lc": artist_name.lower(),
                "updated_at": _now_iso(),
            },
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )
    return {"ok": True, "artist_name": artist_name}


async def audio_studio_v2_unfollow_artist(request: Request, payload: FollowArtistRequest) -> dict[str, Any]:
    user = await require_auth(request)
    artist_name = str(payload.artist_name or "").strip()[:120]
    await db.watch_audio_artist_follows.delete_one(
        {"user_id": user.user_id, "artist_name_lc": artist_name.lower()}
    )
    return {"ok": True, "artist_name": artist_name}


async def audio_studio_v2_daily_drop_inbox(request: Request) -> dict[str, Any]:
    user = await require_auth(request)
    return await _daily_drop_inbox("audio_studio", user, limit=24)


async def audio_studio_v2_mark_listened(request: Request, payload: InboxMarkListenedRequest) -> dict[str, Any]:
    user = await require_auth(request)
    await db[_inbox_status_collection_name("audio_studio")].update_one(
        {"user_id": user.user_id, "item_id": payload.item_id},
        {
            "$set": {
                "user_id": user.user_id,
                "item_id": payload.item_id,
                "listened": True,
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )
    return {"ok": True, "item_id": payload.item_id}


async def audio_studio_v2_admin_conversion_dashboard(request: Request, window_days: int = 7) -> dict[str, Any]:
    await require_admin(request)

    safe_window_days = max(1, min(int(window_days), 30))
    since_dt = datetime.now(timezone.utc) - timedelta(days=safe_window_days)
    since_iso = since_dt.isoformat()

    history_coll = str(SURFACE_CONFIG["audio_studio"]["history_coll"])
    history_projection = {
        "_id": 0,
        "user_id": 1,
        "listen_seconds": 1,
        "completed": 1,
        "created_at": 1,
        "source": 1,
        "device_bucket": 1,
        "geo_country": 1,
    }
    history_rows = await db[history_coll].find(
        {"created_at": {"$gte": since_iso}},
        history_projection,
    ).to_list(60000)

    previous_since_dt = since_dt - timedelta(days=safe_window_days)
    previous_since_iso = previous_since_dt.isoformat()
    previous_history_rows = await db[history_coll].find(
        {"created_at": {"$gte": previous_since_iso, "$lt": since_iso}},
        history_projection,
    ).to_list(60000)

    all_user_ids = {
        str(row.get("user_id") or "").strip()
        for row in (history_rows + previous_history_rows)
        if str(row.get("user_id") or "").strip()
    }

    user_plan_map: dict[str, str] = {}
    if all_user_ids:
        rows = await db.users.find(
            {"user_id": {"$in": list(all_user_ids)}},
            {"_id": 0, "user_id": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
        ).to_list(len(all_user_ids))
        for row in rows:
            uid = str(row.get("user_id") or "").strip()
            if uid:
                user_plan_map[uid] = _normalize_plan(compute_effective_plan(row))

    metrics_current = _compute_metrics_snapshot(history_rows, user_plan_map)
    metrics_previous = _compute_metrics_snapshot(previous_history_rows, user_plan_map)

    source_or_route_query = {
        "$or": [
            {"route": {"$regex": "audio-studio", "$options": "i"}},
            {"source": {"$regex": "audio_studio", "$options": "i"}},
        ]
    }

    prompt_views = int(
        await db.subscription_prompt_telemetry.count_documents(
            {"created_at": {"$gte": since_iso}, **source_or_route_query}
        )
    )

    conversion_rows = await db.subscription_conversion_telemetry.aggregate(
        [
            {"$match": {"created_at": {"$gte": since_iso}, **source_or_route_query}},
            {"$group": {"_id": {"event_type": "$event_type", "plan_id": "$plan_id"}, "count": {"$sum": 1}}},
        ]
    ).to_list(200)

    prev_conversion_rows = await db.subscription_conversion_telemetry.aggregate(
        [
            {"$match": {"created_at": {"$gte": previous_since_iso, "$lt": since_iso}, **source_or_route_query}},
            {"$group": {"_id": {"event_type": "$event_type", "plan_id": "$plan_id"}, "count": {"$sum": 1}}},
        ]
    ).to_list(200)

    plan_cta_clicks = 0
    subscribe_success = 0
    free_to_basic = 0
    free_to_premium = 0

    for row in conversion_rows:
        key = row.get("_id") or {}
        event_type = str(key.get("event_type") or "")
        plan_id = str(key.get("plan_id") or "").lower()
        count = int(row.get("count") or 0)

        if event_type == "plan_cta_click":
            plan_cta_clicks += count
        if event_type == "subscribe_success":
            subscribe_success += count
            if plan_id == "basic":
                free_to_basic += count
            elif plan_id == "premium":
                free_to_premium += count

    prev_plan_cta_clicks = 0
    prev_subscribe_success = 0
    for row in prev_conversion_rows:
        key = row.get("_id") or {}
        event_type = str(key.get("event_type") or "")
        count = int(row.get("count") or 0)
        if event_type == "plan_cta_click":
            prev_plan_cta_clicks += count
        if event_type == "subscribe_success":
            prev_subscribe_success += count

    current_upgrade = {
        "free_engaged": int(metrics_current.get("listener_mix", {}).get("free") or 0),
        "prompt_views": int(prompt_views),
        "plan_cta_clicks": int(plan_cta_clicks),
        "subscribe_success": int(subscribe_success),
        "free_to_basic": int(free_to_basic),
        "free_to_premium": int(free_to_premium),
        "prompt_view_rate_pct": _safe_rate(prompt_views, int(metrics_current.get("listener_mix", {}).get("free") or 0)),
        "cta_rate_pct": _safe_rate(plan_cta_clicks, prompt_views),
        "checkout_success_rate_pct": _safe_rate(subscribe_success, plan_cta_clicks),
        "free_to_paid_rate_pct": _safe_rate(subscribe_success, int(metrics_current.get("listener_mix", {}).get("free") or 0)),
    }
    previous_upgrade = {
        "free_engaged": int(metrics_previous.get("listener_mix", {}).get("free") or 0),
        "plan_cta_clicks": int(prev_plan_cta_clicks),
        "subscribe_success": int(prev_subscribe_success),
        "free_to_paid_rate_pct": _safe_rate(prev_subscribe_success, int(metrics_previous.get("listener_mix", {}).get("free") or 0)),
    }

    benchmark_deltas = {
        "kpis": _compute_benchmark_deltas(metrics_current, metrics_previous),
        "upgrade_funnel": {
            "free_to_paid_rate_pct": {
                "current": float(current_upgrade.get("free_to_paid_rate_pct") or 0),
                "previous": float(previous_upgrade.get("free_to_paid_rate_pct") or 0),
                "delta_abs": _safe_delta_abs(
                    float(current_upgrade.get("free_to_paid_rate_pct") or 0),
                    float(previous_upgrade.get("free_to_paid_rate_pct") or 0),
                ),
                "delta_pct": _safe_delta_pct(
                    float(current_upgrade.get("free_to_paid_rate_pct") or 0),
                    float(previous_upgrade.get("free_to_paid_rate_pct") or 0),
                ),
            },
            "subscribe_success": {
                "current": int(current_upgrade.get("subscribe_success") or 0),
                "previous": int(previous_upgrade.get("subscribe_success") or 0),
                "delta_abs": _safe_delta_abs(
                    float(current_upgrade.get("subscribe_success") or 0),
                    float(previous_upgrade.get("subscribe_success") or 0),
                ),
                "delta_pct": _safe_delta_pct(
                    float(current_upgrade.get("subscribe_success") or 0),
                    float(previous_upgrade.get("subscribe_success") or 0),
                ),
            },
        },
    }

    return {
        "feature_id": "audio-studio",
        "window_days": safe_window_days,
        "benchmark_window_days": safe_window_days,
        "benchmark_previous_window": {
            "from": previous_since_iso,
            "to": since_iso,
        },
        "generated_at": _now_iso(),
        "kpis": {
            "active_listeners": int(metrics_current.get("active_listeners") or 0),
            "total_plays": int(metrics_current.get("total_plays") or 0),
            "completed_plays": int(metrics_current.get("completed_plays") or 0),
            "completion_rate_pct": float(metrics_current.get("completion_rate_pct") or 0),
            "avg_session_length_seconds": float(metrics_current.get("avg_session_length_seconds") or 0),
            "avg_listen_seconds_per_play": float(metrics_current.get("avg_listen_seconds_per_play") or 0),
        },
        "listener_mix": metrics_current.get("listener_mix") or {"free": 0, "basic": 0, "premium": 0},
        "cohort_segmentation": {
            "geo_country": (metrics_current.get("cohorts") or {}).get("geo_country") or {},
            "device_bucket": (metrics_current.get("cohorts") or {}).get("device") or {},
            "channel": (metrics_current.get("cohorts") or {}).get("channel") or {},
        },
        "upgrade_funnel": current_upgrade,
        "benchmark_deltas": benchmark_deltas,
        "contract": {
            "window_bounds_days": [1, 30],
            "deterministic": True,
            "required_kpis": [
                "active_listeners",
                "avg_session_length_seconds",
                "completion_rate_pct",
                "free_to_paid_rate_pct",
            ],
            "required_cohorts": ["geo_country", "device_bucket", "channel"],
            "required_benchmark_metrics": ["avg_session_length_seconds", "completion_rate_pct", "free_to_paid_rate_pct"],
        },
    }
