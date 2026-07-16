from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from .db import db, require_admin


router = APIRouter(prefix="/videos/admin", tags=["Watch Videos Retirement Governance"])

LEGACY_WRAPPER_RETIREMENT_KEY = "watch_videos_legacy_wrapper_retirement"
LEGACY_WRAPPER_TELEMETRY_COLL = "watch_videos_legacy_wrapper_telemetry"

DEFAULT_LEGACY_WRAPPER_RETIREMENT_CONTROLS: dict[str, Any] = {
    "key": LEGACY_WRAPPER_RETIREMENT_KEY,
    "feature_number": 28,
    "feature_id": "watch-videos-audio-podcasts",
    "legacy_retirement_enabled": False,
    "retirement_phase": "observe",
    "retired_legacy_route_families": [],
    "retirement_gate_lookback_hours": 168,
    "retirement_gate_max_events": 0,
    "retirement_gate_max_active_users": 0,
    "retirement_force_apply": False,
    "retirement_override_user_ids": [],
}

WATCH_AUDIO_RETIREMENT_PHASE_TO_FAMILIES: dict[str, list[str]] = {
    "observe": [],
    "phase1_audio_wrappers": ["audio_studio"],
    "phase2_audio_podcasts_wrappers": ["audio_studio", "podcasts"],
}

WATCH_AUDIO_FAMILY_PATH_PREFIX: dict[str, str] = {
    "audio_studio": r"^/api/videos/audio-studio",
    "podcasts": r"^/api/videos/podcasts",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(fallback)


def _parse_simulator_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out[:200]


def _normalize_retirement_phase(raw: Any) -> str:
    phase = str(raw or "observe").strip().lower()
    if phase in WATCH_AUDIO_RETIREMENT_PHASE_TO_FAMILIES:
        return phase
    return "observe"


def _target_retired_route_families(controls: dict[str, Any]) -> list[str]:
    if not bool(controls.get("legacy_retirement_enabled")):
        return []
    phase = _normalize_retirement_phase(controls.get("retirement_phase"))
    return list(WATCH_AUDIO_RETIREMENT_PHASE_TO_FAMILIES.get(phase, []))


def _legacy_family_telemetry_query(route_family: str, since_iso: str) -> dict[str, Any]:
    family = str(route_family or "audio_studio").strip().lower()
    path_prefix = WATCH_AUDIO_FAMILY_PATH_PREFIX.get(family, r"^/api/videos/audio-studio")
    return {
        "created_at": {"$gte": since_iso},
        "$or": [
            {"route_family": family},
            {
                "$and": [
                    {"route_family": {"$exists": False}},
                    {"legacy_path": {"$regex": path_prefix}},
                ]
            },
        ],
    }


async def _future_telemetry_rollup_stub(route_family: str, since_iso: str) -> dict[str, Any]:
    query = _legacy_family_telemetry_query(route_family, since_iso)
    total = await db[LEGACY_WRAPPER_TELEMETRY_COLL].count_documents(query)
    return {
        "route_family": str(route_family),
        "query_since": since_iso,
        "events": int(total),
    }


async def _compute_legacy_retirement_gate_status(
    controls: dict[str, Any],
    route_family: str,
    lookback_hours_override: int | None = None,
) -> dict[str, Any]:
    lookback_hours = max(
        1,
        min(
            _safe_int(
                lookback_hours_override,
                _safe_int(controls.get("retirement_gate_lookback_hours"), 168),
            ),
            24 * 30,
        ),
    )
    max_events = max(0, _safe_int(controls.get("retirement_gate_max_events"), 0))
    max_active_users = max(0, _safe_int(controls.get("retirement_gate_max_active_users"), 0))

    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=lookback_hours)).isoformat()
    query = _legacy_family_telemetry_query(route_family, since_iso)
    override_users = set(_parse_simulator_list(controls.get("retirement_override_user_ids") or []))

    rows = (
        await db[LEGACY_WRAPPER_TELEMETRY_COLL]
        .find(query, {"_id": 0, "user_id": 1, "legacy_path": 1, "created_at": 1})
        .sort("created_at", -1)
        .limit(20000)
        .to_list(20000)
    )
    operational_rows = [
        row for row in rows
        if str(row.get("user_id") or "").strip() not in override_users
    ]

    active_users = {str(row.get("user_id") or "") for row in rows if str(row.get("user_id") or "").strip()}
    by_path: dict[str, int] = {}
    for row in rows:
        path = str(row.get("legacy_path") or "unknown")
        by_path[path] = by_path.get(path, 0) + 1

    total_events = len(rows)
    active_user_count = len(active_users)
    gate_met = total_events <= max_events and active_user_count <= max_active_users

    operational_active_users = {
        str(row.get("user_id") or "")
        for row in operational_rows
        if str(row.get("user_id") or "").strip()
    }
    operational_total_events = len(operational_rows)
    operational_active_user_count = len(operational_active_users)
    operational_gate_met = (
        operational_total_events <= max_events
        and operational_active_user_count <= max_active_users
    )

    events_score = 100.0 if max_events == 0 and total_events == 0 else max(0.0, min(100.0, (max_events / max(total_events, 1)) * 100.0))
    users_score = 100.0 if max_active_users == 0 and active_user_count == 0 else max(0.0, min(100.0, (max_active_users / max(active_user_count, 1)) * 100.0))
    readiness_score = 100.0 if gate_met else round((events_score + users_score) / 2, 2)

    telemetry_stub = await _future_telemetry_rollup_stub(route_family, since_iso)
    return {
        "route_family": str(route_family),
        "lookback_hours": lookback_hours,
        "since": since_iso,
        "total_events": int(total_events),
        "active_users": int(active_user_count),
        "excluded_user_ids": sorted(list(override_users)),
        "gate_thresholds": {
            "max_events": int(max_events),
            "max_active_users": int(max_active_users),
        },
        "gate_met": bool(gate_met),
        "operational_gate": {
            "exclude_synthetic": True,
            "total_events": int(operational_total_events),
            "active_users": int(operational_active_user_count),
            "gate_met": bool(operational_gate_met),
        },
        "readiness_score": readiness_score,
        "top_legacy_paths": sorted(
            [{"path": key, "count": int(value)} for key, value in by_path.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:10],
        "telemetry_scaffold": telemetry_stub,
    }


async def _load_wrapper_retirement_controls() -> dict[str, Any]:
    existing = await db.watch_videos_rollout_controls.find_one(
        {"key": LEGACY_WRAPPER_RETIREMENT_KEY},
        {"_id": 0},
    )
    controls = {**DEFAULT_LEGACY_WRAPPER_RETIREMENT_CONTROLS, **(existing or {})}
    retire_audio_env = str(os.environ.get("RETIRE_VIDEOS_AUDIO_WRAPPERS") or "").strip().lower() in {"1", "true", "yes", "on"}
    retire_podcasts_env = str(os.environ.get("RETIRE_VIDEOS_PODCAST_WRAPPERS") or "").strip().lower() in {"1", "true", "yes", "on"}
    retire_all_env = str(os.environ.get("RETIRE_VIDEOS_AUDIO_PODCAST_WRAPPERS") or "").strip().lower() in {"1", "true", "yes", "on"}
    if retire_all_env:
        retire_audio_env = True
        retire_podcasts_env = True

    if retire_audio_env or retire_podcasts_env:
        controls["legacy_retirement_enabled"] = True
        controls["retirement_phase"] = "phase2_audio_podcasts_wrappers" if retire_audio_env and retire_podcasts_env else "phase1_audio_wrappers"
        controls["retired_legacy_route_families"] = [
            family
            for family in ["audio_studio", "podcasts"]
            if (family == "audio_studio" and retire_audio_env) or (family == "podcasts" and retire_podcasts_env)
        ]
    return controls


@router.get("/legacy-wrapper-retirement-readiness")
async def watch_audio_hub_admin_legacy_wrapper_retirement_readiness(
    request: Request,
    lookback_hours: int = Query(default=168, ge=1, le=24 * 30),
):
    await require_admin(request)

    controls = await _load_wrapper_retirement_controls()
    phase = _normalize_retirement_phase(controls.get("retirement_phase"))
    target_families = WATCH_AUDIO_RETIREMENT_PHASE_TO_FAMILIES.get(phase, []) if bool(controls.get("legacy_retirement_enabled")) else []

    audio_status = await _compute_legacy_retirement_gate_status(controls, "audio_studio", lookback_hours)
    podcast_status = await _compute_legacy_retirement_gate_status(controls, "podcasts", lookback_hours)
    family_readiness = [audio_status, podcast_status]

    audio_operational_gate = bool((audio_status.get("operational_gate") or {}).get("gate_met"))
    podcasts_operational_gate = bool((podcast_status.get("operational_gate") or {}).get("gate_met"))
    recommended_phase = "observe"
    if audio_operational_gate and podcasts_operational_gate:
        recommended_phase = "phase2_audio_podcasts_wrappers"
    elif audio_operational_gate:
        recommended_phase = "phase1_audio_wrappers"

    target_ready = all(
        bool((item.get("operational_gate") or {}).get("gate_met"))
        for item in family_readiness
        if item.get("route_family") in set(target_families)
    ) if target_families else True
    return {
        "generated_at": _now_iso(),
        "feature_number": 28,
        "feature_id": "watch-videos-audio-podcasts",
        "lookback_hours": int(lookback_hours),
        "controls": controls,
        "retirement_phase": phase,
        "target_route_families": target_families,
        "target_phase_gate_ready": bool(target_ready),
        "recommended_phase": recommended_phase,
        "family_readiness": family_readiness,
    }


@router.post("/legacy-wrapper-retirement-controls")
async def watch_audio_hub_admin_legacy_wrapper_retirement_controls(request: Request):
    user = await require_admin(request)

    body = await request.json()
    current = await _load_wrapper_retirement_controls()

    enabled = bool(body.get("legacy_retirement_enabled", current.get("legacy_retirement_enabled", False)))
    phase = _normalize_retirement_phase(body.get("retirement_phase", current.get("retirement_phase", "observe")))
    lookback = max(1, min(_safe_int(body.get("retirement_gate_lookback_hours", current.get("retirement_gate_lookback_hours", 168)), 168), 24 * 30))
    max_events = max(0, _safe_int(body.get("retirement_gate_max_events", current.get("retirement_gate_max_events", 0)), 0))
    max_active_users = max(0, _safe_int(body.get("retirement_gate_max_active_users", current.get("retirement_gate_max_active_users", 0)), 0))
    force_apply = bool(body.get("retirement_force_apply", current.get("retirement_force_apply", False)))
    override_user_ids = _parse_simulator_list(body.get("retirement_override_user_ids", current.get("retirement_override_user_ids") or []))

    draft_controls = {
        **current,
        "legacy_retirement_enabled": enabled,
        "retirement_phase": phase,
        "retirement_gate_lookback_hours": lookback,
        "retirement_gate_max_events": max_events,
        "retirement_gate_max_active_users": max_active_users,
        "retirement_force_apply": force_apply,
        "retirement_override_user_ids": override_user_ids,
    }

    target_families = WATCH_AUDIO_RETIREMENT_PHASE_TO_FAMILIES.get(phase, []) if enabled else []
    audio_status = await _compute_legacy_retirement_gate_status(draft_controls, "audio_studio", lookback)
    podcast_status = await _compute_legacy_retirement_gate_status(draft_controls, "podcasts", lookback)
    family_readiness = [audio_status, podcast_status]

    unmet_targets = [
        item
        for item in family_readiness
        if item.get("route_family") in set(target_families)
        and not bool((item.get("operational_gate") or {}).get("gate_met"))
    ]
    if enabled and target_families and unmet_targets and not force_apply:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Telemetry gate not met for requested wrapper retirement phase.",
                "target_route_families": target_families,
                "unmet_targets": unmet_targets,
                "hint": "Either relax thresholds or set retirement_force_apply=true.",
            },
        )

    updates = {
        "legacy_retirement_enabled": enabled,
        "retirement_phase": phase,
        "retired_legacy_route_families": target_families,
        "retirement_gate_lookback_hours": lookback,
        "retirement_gate_max_events": max_events,
        "retirement_gate_max_active_users": max_active_users,
        "retirement_force_apply": force_apply,
        "retirement_override_user_ids": override_user_ids,
        "retirement_last_gate_snapshot": {
            "audio_studio": audio_status,
            "podcasts": podcast_status,
        },
        "retirement_updated_by": user.user_id,
        "retirement_updated_at": _now_iso(),
    }

    await db.watch_videos_rollout_controls.update_one(
        {"key": LEGACY_WRAPPER_RETIREMENT_KEY},
        {
            "$set": updates,
            "$setOnInsert": {
                "key": LEGACY_WRAPPER_RETIREMENT_KEY,
                "feature_number": 28,
                "feature_id": "watch-videos-audio-podcasts",
            },
        },
        upsert=True,
    )

    return {
        "success": True,
        "generated_at": _now_iso(),
        "controls": {**current, **updates},
        "family_readiness": family_readiness,
    }


@router.get("/legacy-wrapper-removal-readiness")
async def watch_audio_hub_admin_legacy_wrapper_removal_readiness(
    request: Request,
    lookback_hours: int = Query(default=168, ge=1, le=24 * 30),
):
    await require_admin(request)
    controls = await _load_wrapper_retirement_controls()
    audio_status = await _compute_legacy_retirement_gate_status(controls, "audio_studio", lookback_hours)
    podcasts_status = await _compute_legacy_retirement_gate_status(controls, "podcasts", lookback_hours)
    families = [audio_status, podcasts_status]

    strict_zero_ready = bool(
        all(bool((row.get("operational_gate") or {}).get("gate_met")) for row in families)
    )
    return {
        "generated_at": _now_iso(),
        "feature_number": 28,
        "feature_id": "watch-videos-audio-podcasts",
        "lookback_hours": int(lookback_hours),
        "controls_snapshot": {
            "legacy_retirement_enabled": bool(controls.get("legacy_retirement_enabled")),
            "retirement_phase": _normalize_retirement_phase(controls.get("retirement_phase")),
            "retired_legacy_route_families": _target_retired_route_families(controls),
            "retirement_override_user_ids": _parse_simulator_list(controls.get("retirement_override_user_ids") or []),
        },
        "strict_zero_operational_ready": strict_zero_ready,
        "ready_for_legacy_code_removal": strict_zero_ready,
        "family_readiness": families,
    }


@router.post("/legacy-wrapper-hard-delete")
async def watch_audio_hub_admin_legacy_wrapper_hard_delete(request: Request):
    user = await require_admin(request)
    body = await request.json()
    lookback_hours = max(1, min(_safe_int(body.get("lookback_hours", 168), 168), 24 * 30))
    target_families = {
        str(item or "").strip().lower()
        for item in (body.get("route_families") or ["audio_studio", "podcasts"])
    }
    target_families = {item for item in target_families if item in {"audio_studio", "podcasts"}}
    if not target_families:
        raise HTTPException(status_code=400, detail="route_families must include audio_studio and/or podcasts")

    controls = await _load_wrapper_retirement_controls()
    statuses = {
        "audio_studio": await _compute_legacy_retirement_gate_status(controls, "audio_studio", lookback_hours),
        "podcasts": await _compute_legacy_retirement_gate_status(controls, "podcasts", lookback_hours),
    }
    unmet = [
        statuses[family]
        for family in target_families
        if not bool((statuses[family].get("operational_gate") or {}).get("gate_met"))
    ]
    if unmet:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Strict-zero operational gate not met for wrapper hard-delete.",
                "unmet_targets": unmet,
                "hint": "Wait for sustained zero-consumer window or widen retirement_override_user_ids if synthetic-only traffic.",
            },
        )

    hard_deleted = sorted(list(target_families))
    update_payload = {
        "legacy_wrapper_hard_delete_ready": True,
        "legacy_wrapper_hard_deleted_families": hard_deleted,
        "legacy_wrapper_hard_delete_checked_at": _now_iso(),
        "legacy_wrapper_hard_delete_checked_by": user.user_id,
        "legacy_wrapper_hard_delete_lookback_hours": int(lookback_hours),
    }
    await db.watch_videos_rollout_controls.update_one(
        {"key": LEGACY_WRAPPER_RETIREMENT_KEY},
        {
            "$set": update_payload,
            "$setOnInsert": {
                "key": LEGACY_WRAPPER_RETIREMENT_KEY,
                "feature_number": 28,
                "feature_id": "watch-videos-audio-podcasts",
            },
        },
        upsert=True,
    )
    return {
        "success": True,
        "hard_delete_ready": True,
        "hard_deleted_families": hard_deleted,
        "lookback_hours": int(lookback_hours),
        "evidence": statuses,
    }
