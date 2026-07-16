"""Watch Videos premium hub (Netflix + YouTube style feed, player, and recommendation intelligence)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import hashlib
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any
import uuid
import requests

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage

from .db import EMERGENT_LLM_KEY, User, db, require_auth, resolve_user_role
from services.watch_videos_catalog_service import WatchVideosCatalogService
from services.watch_videos_recommendation_service import WatchVideosRecommendationService
from services.watch_videos_playback_service import WatchVideosPlaybackService
from utils.access_control_engine import build_session_entitlements, compute_effective_plan
from utils.email_notifications import notify


router = APIRouter(prefix="/videos", tags=["Watch Videos"])
logger = logging.getLogger("routes.watch_videos")

FEATURE_ID = "watch-videos"
FEATURE_ROUTE = "/features/watch-videos"
STATE_FLAG_KEY = "watch_videos_daily_drop_state"
VISUAL_REFRESH_STATE_KEY = "watch_videos_visual_refresh_state"
VISUAL_REFRESH_VERSION = "watch-videos-v3-2026-05-11"
CATALOG_CONTENT_STATE_KEY = "watch_videos_catalog_content_state"
CATALOG_CONTENT_VERSION = "watch-videos-v9-saga-continuity-2026-05-12"

COLL_CATALOG = "watch_video_catalog"
COLL_WATCH_HISTORY = "watch_video_watch_history"
COLL_WATCH_USAGE = "watch_video_usage_log"
COLL_INGEST_RUNS = "watch_video_ingest_runs"
COLL_FEEDBACK = "watch_video_feedback"
COLL_WATCHLIST = "watch_video_watchlist"
COLL_PREFS = "watch_video_user_preferences"
COLL_VISUAL_THEME = "watch_video_visual_theme_config"
COLL_API_OBSERVABILITY = "watch_video_api_observability"

PLAN_LEVEL = {"free": 0, "basic": 1, "premium": 2}
# Rebuild recommendation:
PLAN_DAILY_WATCH_CAPS = {"free": 5, "basic": 120, "premium": -1}
STYLE_PACKS = {"cinematic", "documentary", "creator"}

SEED_TARGET_COUNT = 520
DAILY_DROP_COUNT = 5
MAX_CATEGORY_ROWS = 12

VIDEO_DISCOVERY_QUERIES: list[tuple[str, str, str]] = [
    ("Action", "action", "feature_films"),
    ("Adventure", "adventure", "feature_films"),
    ("Drama", "drama", "feature_films"),
    ("Thriller", "thriller", "feature_films"),
    ("Crime", "crime", "feature_films"),
    ("Mystery", "mystery", "feature_films"),
    ("Sci-Fi", "science fiction", "feature_films"),
    ("Fantasy", "fantasy", "feature_films"),
    ("Horror", "horror", "feature_films"),
    ("Comedy", "comedy", "feature_films"),
    ("Romance", "romance", "feature_films"),
    ("Animation", "animation", "feature_films"),
    ("Family", "family", "feature_films"),
    ("War", "war", "feature_films"),
    ("History", "history", "feature_films"),
    ("Biography", "biography", "feature_films"),
    ("Sports", "sports", "feature_films"),
    ("Documentary", "documentary", "feature_films"),
    ("Indie", "indie", "feature_films"),
    ("Noir", "noir", "feature_films"),
    ("Musical", "musical", "feature_films"),
    ("Psychological", "psychological", "feature_films"),
    ("Political", "political", "feature_films"),
    ("Epic", "epic", "feature_films"),
    ("Classics", "classic", "feature_films"),
    ("Series Episodes", "episode", "classic_tv"),
    ("Crime Episodes", "crime", "classic_tv"),
    ("Fantasy Episodes", "fantasy", "classic_tv"),
    ("Sci-Fi Episodes", "science fiction", "classic_tv"),
    ("Comedy Episodes", "comedy", "classic_tv"),
]

_REAL_VIDEO_POOL_CACHE: list[dict[str, Any]] = []
_REAL_VIDEO_POOL_CACHE_TS: datetime | None = None


VIDEO_ASSETS: list[dict[str, Any]] = [
    {
        "video_url": "https://samplelib.com/lib/preview/mp4/sample-5s.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-5s.jpg",
        "duration_seconds": 305,
    },
    {
        "video_url": "https://samplelib.com/lib/preview/mp4/sample-10s.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-10s.jpg",
        "duration_seconds": 540,
    },
    {
        "video_url": "https://samplelib.com/lib/preview/mp4/sample-15s.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-15s.jpg",
        "duration_seconds": 860,
    },
    {
        "video_url": "https://samplelib.com/lib/preview/mp4/sample-20s.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-20s.jpg",
        "duration_seconds": 1210,
    },
    {
        "video_url": "https://samplelib.com/lib/preview/mp4/sample-30s.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-30s.jpg",
        "duration_seconds": 1790,
    },
    {
        "video_url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-30s.jpg",
        "duration_seconds": 640,
    },
    {
        "video_url": "https://www.w3schools.com/html/mov_bbb.mp4",
        "thumbnail_url": "https://samplelib.com/lib/preview/mp4/sample-20s.jpg",
        "duration_seconds": 760,
    },
]


REAL_VIDEO_LIBRARY: list[dict[str, Any]] = [
    {
        "title": "Interstellar — Official Trailer",
        "description": "Official trailer from the Interstellar campaign.",
        "category": "Cinema",
        "studio": "Warner Bros. Pictures",
        "youtube_video_id": "zSWdZVtXT7E",
        "thumbnail_url": "https://i.ytimg.com/vi/zSWdZVtXT7E/hqdefault.jpg",
        "duration_seconds": 185,
        "year": 2014,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "cinema", "space", "drama"],
    },
    {
        "title": "Inception — Official Trailer",
        "description": "Official trailer for Inception.",
        "category": "Sci-Fi",
        "studio": "Warner Bros. Pictures",
        "youtube_video_id": "YoHD9XEInc0",
        "thumbnail_url": "https://i.ytimg.com/vi/YoHD9XEInc0/hqdefault.jpg",
        "duration_seconds": 148,
        "year": 2010,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "mind-bending", "sci-fi", "action"],
    },
    {
        "title": "Avengers: Endgame — Official Trailer",
        "description": "Official trailer for Avengers: Endgame.",
        "category": "Actions",
        "studio": "Marvel Entertainment",
        "youtube_video_id": "TcMBFSGVi1c",
        "thumbnail_url": "https://i.ytimg.com/vi/TcMBFSGVi1c/hqdefault.jpg",
        "duration_seconds": 152,
        "year": 2019,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "marvel", "superhero", "blockbuster"],
    },
    {
        "title": "Avengers: Infinity War — Official Trailer",
        "description": "Official trailer for Avengers: Infinity War.",
        "category": "Actions",
        "studio": "Marvel Entertainment",
        "youtube_video_id": "6ZfuNTqbHE8",
        "thumbnail_url": "https://i.ytimg.com/vi/6ZfuNTqbHE8/hqdefault.jpg",
        "duration_seconds": 150,
        "year": 2018,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "marvel", "action", "heroes"],
    },
    {
        "title": "Spider-Man: No Way Home — Official Trailer",
        "description": "Official trailer for Spider-Man: No Way Home.",
        "category": "Hollywood",
        "studio": "Sony Pictures Entertainment",
        "youtube_video_id": "JfVOs4VSpmA",
        "thumbnail_url": "https://i.ytimg.com/vi/JfVOs4VSpmA/hqdefault.jpg",
        "duration_seconds": 174,
        "year": 2021,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "spiderman", "hollywood", "action"],
    },
    {
        "title": "The Dark Knight — Official Trailer",
        "description": "Official trailer for The Dark Knight.",
        "category": "Thriller",
        "studio": "Warner Bros. Pictures",
        "youtube_video_id": "EXeTwQWrcwY",
        "thumbnail_url": "https://i.ytimg.com/vi/EXeTwQWrcwY/hqdefault.jpg",
        "duration_seconds": 146,
        "year": 2008,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "thriller", "batman", "crime"],
    },
    {
        "title": "Top Gun: Maverick — Official Trailer",
        "description": "Official trailer for Top Gun: Maverick.",
        "category": "Actions",
        "studio": "Paramount Pictures",
        "youtube_video_id": "qSqVVswa420",
        "thumbnail_url": "https://i.ytimg.com/vi/qSqVVswa420/hqdefault.jpg",
        "duration_seconds": 154,
        "year": 2022,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "jets", "action", "cinema"],
    },
    {
        "title": "Dune: Part Two — Official Trailer",
        "description": "Official trailer for Dune: Part Two.",
        "category": "Sci-Fi",
        "studio": "Warner Bros. Pictures",
        "youtube_video_id": "Way9Dexny3w",
        "thumbnail_url": "https://i.ytimg.com/vi/Way9Dexny3w/hqdefault.jpg",
        "duration_seconds": 189,
        "year": 2024,
        "rating": "PG-13",
        "language": "English",
        "tags": ["trailer", "sci-fi", "desert", "cinema"],
    },
    {
        "title": "NASA Live: Earth From Space",
        "description": "Official NASA live feed and updates from Earth orbit.",
        "category": "Discovery",
        "studio": "NASA",
        "youtube_video_id": "21X5lGlDOfg",
        "thumbnail_url": "https://i.ytimg.com/vi/21X5lGlDOfg/hqdefault_live.jpg",
        "duration_seconds": 3600,
        "year": 2026,
        "rating": "PG",
        "language": "English",
        "tags": ["nasa", "live", "space", "science"],
    },
    {
        "title": "Planet Earth Highlights",
        "description": "Wildlife and nature highlights from documentary creators.",
        "category": "Documentary",
        "studio": "BBC Earth",
        "youtube_video_id": "c8aFcHFu8QM",
        "thumbnail_url": "https://i.ytimg.com/vi/c8aFcHFu8QM/hqdefault.jpg",
        "duration_seconds": 408,
        "year": 2021,
        "rating": "PG",
        "language": "English",
        "tags": ["nature", "documentary", "earth", "wildlife"],
    },
    {
        "title": "Big Buck Bunny — 60fps",
        "description": "Open movie short used for player compatibility testing.",
        "category": "Kids",
        "studio": "Blender Foundation",
        "youtube_video_id": "aqz-KE-bpKQ",
        "thumbnail_url": "https://i.ytimg.com/vi/aqz-KE-bpKQ/hqdefault.jpg",
        "duration_seconds": 596,
        "year": 2020,
        "rating": "PG",
        "language": "English",
        "tags": ["animation", "open-movie", "family", "kids"],
    },
    {
        "title": "YouTube API Demo Video",
        "description": "Classic demo video used for YouTube player and embed testing.",
        "category": "Technology",
        "studio": "Google Developers",
        "youtube_video_id": "M7lc1UVf-VE",
        "thumbnail_url": "https://i.ytimg.com/vi/M7lc1UVf-VE/hqdefault.jpg",
        "duration_seconds": 233,
        "year": 2012,
        "rating": "PG",
        "language": "English",
        "tags": ["youtube", "api", "developer", "technology"],
    },
]


CATEGORY_PROFILES: list[dict[str, Any]] = [
    {
        "name": "Actions",
        "tags": ["stunts", "adventure", "speed", "missions"],
        "studios": ["Apex Motion", "Iron Scene", "Velocity House"],
    },
    {
        "name": "Drama",
        "tags": ["character", "emotion", "journey", "legacy"],
        "studios": ["StageCraft", "NorthFrame", "Arc Drama Works"],
    },
    {
        "name": "Cinema",
        "tags": ["filmcraft", "director-cut", "visuals", "festival"],
        "studios": ["Cinema Lab", "Auteur Collective", "Silver Prism"],
    },
    {
        "name": "Discovery",
        "tags": ["science", "exploration", "earth", "innovation"],
        "studios": ["DiscoverX", "Orbital Docs", "Blue Planet Studio"],
    },
    {
        "name": "Hollywood",
        "tags": ["premiere", "blockbuster", "studio", "behind-scenes"],
        "studios": ["Sunset Media", "Hollywood Prime", "Westline Studios"],
    },
    {
        "name": "Documentary",
        "tags": ["real-story", "history", "context", "interviews"],
        "studios": ["DocuSource", "GroundTruth Films", "Signal Documentary"],
    },
    {
        "name": "Sci-Fi",
        "tags": ["future", "space", "ai", "dystopia"],
        "studios": ["Nova Fiction", "Quantum Reel", "Spacebound Works"],
    },
    {
        "name": "Comedy",
        "tags": ["humor", "satire", "standup", "feel-good"],
        "studios": ["Laughline", "Comedy Nest", "Sketch Republic"],
    },
    {
        "name": "Thriller",
        "tags": ["mystery", "crime", "plot-twist", "investigation"],
        "studios": ["Noir Control", "Dark Signal", "Pulse Thriller Co"],
    },
    {
        "name": "Romance",
        "tags": ["relationships", "love", "heart", "connection"],
        "studios": ["Heartline", "Roselight", "Love Story House"],
    },
    {
        "name": "Sports",
        "tags": ["athlete", "training", "competition", "highlights"],
        "studios": ["Arena Studio", "Playmaker Films", "Momentum Sports"],
    },
    {
        "name": "Kids",
        "tags": ["family", "animation", "learning", "fun"],
        "studios": ["KidSpark", "PlayPlanet", "Wonder Junior"],
    },
    {
        "name": "Music",
        "tags": ["concert", "studio", "sound", "artists"],
        "studios": ["SoundGrid", "Music Prism", "LiveWave"],
    },
    {
        "name": "Technology",
        "tags": ["engineering", "product", "startups", "systems"],
        "studios": ["TechFrame", "Future Systems TV", "BuildOps Media"],
    },
]

LANGUAGES = ["English", "Spanish", "French", "Hindi", "Japanese", "Korean"]
RATINGS = ["PG", "PG-13", "U/A 13+", "U/A 16+"]


class WatchEventRequest(BaseModel):
    video_id: str = Field(min_length=6, max_length=120)
    progress_seconds: int = Field(default=0, ge=0, le=86400)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    completed: bool = False
    source: str = Field(default="player", max_length=40)


class VideoFeedbackRequest(BaseModel):
    video_id: str = Field(min_length=6, max_length=120)
    feedback: str = Field(pattern="^(like|dislike|clear)$")


class VideoWatchlistToggleRequest(BaseModel):
    video_id: str = Field(min_length=6, max_length=120)
    action: str = Field(default="toggle", pattern="^(toggle|add|remove)$")


class VideoVisualPreferencesUpdateRequest(BaseModel):
    show_recommendation_reasons: bool | None = None
    watchlist_sort_mode: str | None = Field(default=None, pattern="^(recent|duration|category)$")
    watchlist_sort_direction: str | None = Field(default=None, pattern="^(asc|desc)$")
    autoplay_next_enabled: bool | None = None


class VideoStylePackUpdateRequest(BaseModel):
    category: str = Field(default="all", max_length=60)
    style_pack: str = Field(pattern="^(cinematic|documentary|creator)$")


class VideoRegenerateThemeRequest(BaseModel):
    force_new_cycle: bool = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _today_key() -> str:
    return _now().strftime("%Y-%m-%d")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    return cleaned.strip("-") or "general"


def _thumbnail_variant_seed(seed_key: str, category: str, variant: int = 0, style_pack: str = "cinematic", theme_cycle: str = "base") -> str:
    digest = hashlib.sha1(f"{seed_key}|{category}|{variant}|{style_pack}|{theme_cycle}".encode("utf-8")).hexdigest()[:18]
    return f"wv-{_slugify(category)}-{digest}"


def _dynamic_thumbnail_url(
    seed_key: str,
    category: str,
    variant: int = 0,
    *,
    style_pack: str = "cinematic",
    theme_cycle: str = "base",
) -> str:
    # Deterministic high-quality public image source with unique seeded variants.
    selected_pack = style_pack if style_pack in STYLE_PACKS else "cinematic"
    seed = _thumbnail_variant_seed(seed_key, category, variant, selected_pack, theme_cycle)
    base = f"https://picsum.photos/seed/{seed}/1280/720"
    if selected_pack == "documentary":
        return f"{base}?grayscale"
    if selected_pack == "creator":
        return f"{base}?blur=1"
    return base


def _resolve_plan(user: User) -> str:
    plan = compute_effective_plan(_build_user_doc(user))
    return plan if plan in PLAN_LEVEL else "free"


def _scope_label(plan: str) -> str:
    if plan == "premium":
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


def _elapsed_ms(started_at: datetime) -> int:
    return max(0, int((_now() - started_at).total_seconds() * 1000))


def _safe_pct(numerator: int | float, denominator: int | float) -> float:
    safe_denominator = float(denominator or 0)
    if safe_denominator <= 0:
        return 0.0
    return round((float(numerator or 0) / safe_denominator) * 100.0, 2)


def _percentile(values: list[int | float], pct: float) -> int:
    clean = sorted([max(0, int(v or 0)) for v in values])
    if not clean:
        return 0
    if len(clean) == 1:
        return int(clean[0])

    rank = (len(clean) - 1) * (max(0.0, min(100.0, float(pct))) / 100.0)
    lower = int(rank)
    upper = min(len(clean) - 1, lower + 1)
    if lower == upper:
        return int(clean[lower])

    weight = rank - lower
    interpolated = (clean[lower] * (1 - weight)) + (clean[upper] * weight)
    return int(round(interpolated))


def _observability_incident_actions(signal_type: str) -> list[str]:
    signal = str(signal_type or "").strip().lower()
    if signal == "error_spike":
        return [
            "Inspect failing watch/feedback requests and retry patterns in the same hour",
            "Run admin observability refresh and verify if errors drop in the next window",
        ]
    if signal == "latency_spike":
        return [
            "Prioritize low-latency playback paths and monitor p95 for the next 2 hours",
            "Review heavy watchlist/catalog interactions driving queue contention",
        ]
    if signal == "quota_spike":
        return [
            "Surface upgrade nudges for capped users in high-pressure hours",
            "Review plan-cap messaging to reduce repeated quota rejection retries",
        ]
    return [
        "Continue monitoring this interval for sustained anomalies",
    ]


def _build_incident_timeline_csv(incident_timeline: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "hour_bucket",
            "signal_type",
            "severity",
            "title",
            "total_calls",
            "error_rate_pct",
            "watch_error_rate_pct",
            "watch_p95_ms",
            "quota_rejections",
            "suggested_actions",
        ]
    )

    if not incident_timeline:
        writer.writerow(
            [
                _now_iso(),
                "none",
                "low",
                "No major spikes detected",
                0,
                0.0,
                0.0,
                0,
                0,
                "No immediate action required",
            ]
        )
        return output.getvalue()

    for incident in incident_timeline:
        metrics = incident.get("metrics") or {}
        actions = incident.get("suggested_actions") or []
        writer.writerow(
            [
                str(incident.get("hour_bucket") or ""),
                str(incident.get("signal_type") or ""),
                str(incident.get("severity") or ""),
                str(incident.get("title") or ""),
                int(metrics.get("total_calls") or 0),
                round(float(metrics.get("error_rate_pct") or 0.0), 2),
                round(float(metrics.get("watch_error_rate_pct") or 0.0), 2),
                int(metrics.get("watch_p95_ms") or 0),
                int(metrics.get("quota_rejections") or 0),
                " | ".join(str(action) for action in actions if str(action).strip()),
            ]
        )

    return output.getvalue()


async def _record_api_observability(
    *,
    endpoint: str,
    user_id: str,
    plan: str,
    status_code: int,
    duration_ms: int,
    source: str = "",
    error_code: str = "",
) -> None:
    try:
        await db[COLL_API_OBSERVABILITY].insert_one(
            {
                "event_id": f"wv_obs_{uuid.uuid4().hex[:12]}",
                "feature_id": FEATURE_ID,
                "endpoint": str(endpoint or "unknown")[:64],
                "user_id": str(user_id or "")[:80],
                "plan": str(plan or "free")[:24],
                "status_code": int(status_code),
                "duration_ms": max(0, int(duration_ms or 0)),
                "source": str(source or "")[:60],
                "error_code": str(error_code or "")[:160],
                "day_key": _today_key(),
                "created_at": _now_iso(),
            }
        )
    except Exception as telemetry_exc:
        logger.warning("watch_videos_observability_write_failed: %s", telemetry_exc)


def _default_category_style_packs() -> dict[str, str]:
    return {str(profile.get("name") or "General"): "cinematic" for profile in CATEGORY_PROFILES}


async def _get_visual_theme_config() -> dict[str, Any]:
    row = await db[COLL_VISUAL_THEME].find_one({"key": FEATURE_ID}, {"_id": 0}) or {}
    style_map = _default_category_style_packs()
    existing = row.get("category_style_packs") if isinstance(row.get("category_style_packs"), dict) else {}
    for category, pack in existing.items():
        pack_name = str(pack or "cinematic")
        if pack_name in STYLE_PACKS:
            style_map[str(category)] = pack_name

    return {
        "theme_cycle": str(row.get("theme_cycle") or "cycle-default"),
        "default_style_pack": str(row.get("default_style_pack") or "cinematic"),
        "category_style_packs": style_map,
        "updated_at": str(row.get("updated_at") or ""),
    }


async def _save_visual_theme_config(config: dict[str, Any]) -> dict[str, Any]:
    now_iso = _now_iso()
    normalized = {
        "theme_cycle": str(config.get("theme_cycle") or "cycle-default"),
        "default_style_pack": str(config.get("default_style_pack") or "cinematic"),
        "category_style_packs": {
            str(category): (str(pack) if str(pack) in STYLE_PACKS else "cinematic")
            for category, pack in (config.get("category_style_packs") or {}).items()
        },
        "updated_at": now_iso,
    }
    await db[COLL_VISUAL_THEME].update_one(
        {"key": FEATURE_ID},
        {
            "$set": {
                "key": FEATURE_ID,
                **normalized,
            },
            "$setOnInsert": {"created_at": now_iso},
        },
        upsert=True,
    )
    return normalized


async def _apply_visual_theme_to_catalog(
    catalog_coll,
    *,
    video_ids: list[str] | None = None,
    category_filter: str | None = None,
) -> dict[str, Any]:
    config = await _get_visual_theme_config()
    style_map = config.get("category_style_packs") if isinstance(config.get("category_style_packs"), dict) else {}
    default_pack = str(config.get("default_style_pack") or "cinematic")
    theme_cycle = str(config.get("theme_cycle") or "cycle-default")

    query: dict[str, Any] = {}
    if video_ids:
        query["video_id"] = {"$in": [str(video_id) for video_id in video_ids if str(video_id)]}
    if category_filter:
        query["category"] = str(category_filter)

    rows = await catalog_coll.find(
        query,
        {
            "_id": 0,
            "video_id": 1,
            "category": 1,
            "source_template_id": 1,
            "youtube_video_id": 1,
            "thumbnail_locked": 1,
        },
    ).to_list(5000)
    if not rows:
        return {"status": "no_rows", "updated_count": 0, "theme_cycle": theme_cycle}

    now_iso = _now_iso()
    updated = 0
    for idx, row in enumerate(rows):
        video_id = str(row.get("video_id") or "").strip()
        if not video_id:
            continue
        if bool(row.get("thumbnail_locked")) and str(row.get("youtube_video_id") or ""):
            continue
        category = str(row.get("category") or "General")
        style_pack = str(style_map.get(category) or default_pack)
        seed_key = str(row.get("source_template_id") or video_id)
        thumbnail_url = _dynamic_thumbnail_url(
            seed_key,
            category,
            idx % 11,
            style_pack=style_pack,
            theme_cycle=theme_cycle,
        )
        await catalog_coll.update_one(
            {"video_id": video_id},
            {"$set": {"thumbnail_url": thumbnail_url, "updated_at": now_iso}},
        )
        updated += 1

    return {
        "status": "applied",
        "updated_count": int(updated),
        "theme_cycle": theme_cycle,
        "category_filter": str(category_filter or ""),
    }


def _build_user_doc(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "full_access": bool(user.full_access),
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "subscription_end_date": user.subscription_end_date,
        "payment_verified": bool(getattr(user, "payment_verified", False)),
        "subscription_permanent": bool(user.subscription_permanent),
        "platform_role": user.platform_role,
        "employee_permissions": list(user.employee_permissions or []),
        "pending_subscription_transition": user.pending_subscription_transition,
    }


def _daily_watch_limit(user: User, plan: str) -> int:
    entitlements = build_session_entitlements(_build_user_doc(user)).get("feature_entitlements") or {}
    entitlement_limit = entitlements.get("watch_videos_daily_watch_cap")
    if isinstance(entitlement_limit, int):
        return int(entitlement_limit)
    return int(PLAN_DAILY_WATCH_CAPS.get(plan, 0))


def _visible_plan_values(plan: str) -> list[str]:
    max_level = PLAN_LEVEL.get(plan, 0)
    return [name for name, level in PLAN_LEVEL.items() if level <= max_level]


def _visibility_filter(plan: str) -> dict[str, Any]:
    return {
        "is_active": {"$ne": False},
        "min_plan": {"$in": _visible_plan_values(plan)},
    }


def _youtube_embed_url(video_id: str) -> str:
    clean_id = str(video_id or "").strip()
    if not clean_id:
        return ""
    return f"https://www.youtube-nocookie.com/embed/{clean_id}?rel=0&modestbranding=1&playsinline=1"


def _real_video_discovery_pool() -> list[dict[str, Any]]:
    global _REAL_VIDEO_POOL_CACHE, _REAL_VIDEO_POOL_CACHE_TS
    if _REAL_VIDEO_POOL_CACHE and _REAL_VIDEO_POOL_CACHE_TS and (_now() - _REAL_VIDEO_POOL_CACHE_TS).total_seconds() < 12 * 3600:
        return list(_REAL_VIDEO_POOL_CACHE)

    discovered: list[dict[str, Any]] = []
    seen_identifiers: set[str] = set()
    try:
        for category, keyword, collection in VIDEO_DISCOVERY_QUERIES:
            search = requests.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": f"collection:({collection}) AND mediatype:(movies) AND ({keyword})",
                    "fl[]": ["identifier", "title", "creator", "description", "year"],
                    "rows": 8,
                    "output": "json",
                },
                timeout=12,
            )
            docs = ((search.json() or {}).get("response") or {}).get("docs") or []
            for doc in docs[:4]:
                identifier = str(doc.get("identifier") or "").strip()
                if not identifier or identifier in seen_identifiers:
                    continue
                seen_identifiers.add(identifier)

                metadata = requests.get(f"https://archive.org/metadata/{identifier}", timeout=8)
                files = (metadata.json() or {}).get("files") or []
                candidates = []
                for f in files:
                    name = str(f.get("name") or "")
                    lowered_name = name.lower()
                    fmt = str(f.get("format") or "").lower()
                    if not (lowered_name.endswith(".mp4") or "h.264" in fmt or "mpeg4" in fmt):
                        continue
                    try:
                        size = int(f.get("size") or 0)
                    except Exception:
                        size = 0
                    try:
                        duration = float(f.get("length") or 0)
                    except Exception:
                        duration = 0.0
                    candidates.append((size, duration, name))

                if not candidates:
                    continue
                candidates.sort(key=lambda row: row[0], reverse=True)
                _, duration, best_name = candidates[0]
                video_url = f"https://archive.org/download/{identifier}/{requests.utils.requote_uri(best_name)}"

                title = str(doc.get("title") or identifier).strip()[:180]
                studio = str(doc.get("creator") or "Archive Studio").strip()[:120]
                year_raw = str(doc.get("year") or "").strip()
                if year_raw.isdigit() and len(year_raw) >= 4:
                    year = int(year_raw[:4])
                else:
                    year = _now().year
                description = str(doc.get("description") or f"Official archive release: {title}").strip()[:1400]
                thumbnail = f"https://archive.org/download/{identifier}/__ia_thumb.jpg"
                is_episode = collection == "classic_tv"

                discovered.append(
                    {
                        "title": title,
                        "description": description,
                        "category": category,
                        "studio": studio,
                        "video_url": video_url,
                        "fallback_video_url": video_url,
                        "playback_type": "mp4",
                        "youtube_video_id": "",
                        "thumbnail_url": thumbnail,
                        "duration_seconds": int(duration or 180),
                        "year": year,
                        "rating": "PG",
                        "language": "English",
                        "tags": [
                            str(category).lower().replace(" ", "-"),
                            "official",
                            "movie-episode" if is_episode else "movie-release",
                            "real-video",
                            "public-domain",
                        ],
                        "source_label": "Archive Official Release",
                        "source_trust_badge": "Official",
                        "source_channel": studio,
                    }
                )
                if len(discovered) >= 620:
                    break
            if len(discovered) >= 620:
                break
    except Exception:
        discovered = []

    if not discovered:
        discovered = []

    _REAL_VIDEO_POOL_CACHE = discovered
    _REAL_VIDEO_POOL_CACHE_TS = _now()
    return list(_REAL_VIDEO_POOL_CACHE)


def _derive_source_trust_badge(*, title: str, tags: list[str], playback_type: str) -> str:
    lowered_title = str(title or "").strip().lower()
    lowered_tags = {str(tag or "").strip().lower() for tag in (tags or []) if str(tag or "").strip()}

    if "trailer" in lowered_title or "trailer" in lowered_tags:
        return "Trailer"
    if (
        "clip" in lowered_title
        or "highlights" in lowered_title
        or "clip" in lowered_tags
        or "highlights" in lowered_tags
    ):
        return "Clip"
    if str(playback_type or "").strip().lower() == "youtube":
        return "Official"
    return "Clip"


def _derive_source_channel(studio: str) -> str:
    channel = str(studio or "").strip()
    return channel[:64] if channel else "Verified Channel"


def _derive_saga_metadata(title: str, category: str, studio: str, index: int) -> dict[str, Any]:
    text = f"{title} {category} {studio}".lower()
    saga_map = [
        ("avengers", "Avengers Saga"),
        ("spider-man", "Spider-Man Saga"),
        ("batman", "Batman Saga"),
        ("star wars", "Star Wars Saga"),
        ("mission impossible", "Mission: Impossible Saga"),
        ("fast", "Fast Saga"),
        ("harry potter", "Harry Potter Saga"),
        ("lord of the rings", "Middle-earth Saga"),
        ("jurassic", "Jurassic Saga"),
        ("matrix", "Matrix Saga"),
    ]
    for key, saga in saga_map:
        if key in text:
            order = (index % 6) + 1
            return {
                "saga_key": key.replace(" ", "-"),
                "saga_name": saga,
                "saga_order": order,
                "spoiler_safe_recap": f"Recap: {saga} momentum continues with bigger stakes and new turns.",
            }

    fallback_key = f"{str(studio or 'studio').strip().lower().replace(' ', '-')}-{str(category or 'genre').strip().lower().replace(' ', '-') }"
    return {
        "saga_key": fallback_key[:64],
        "saga_name": f"{studio} {category} Arc".strip()[:80],
        "saga_order": (index % 5) + 1,
        "spoiler_safe_recap": f"Recap: continue this {category.lower()} arc with no spoilers, just key momentum cues.",
    }


def _combined_real_video_library() -> list[dict[str, Any]]:
    discovered = _real_video_discovery_pool()
    movie_like_categories = {
        "cinema",
        "hollywood",
        "action",
        "actions",
        "sci-fi",
        "science-fiction",
        "fantasy",
        "drama",
        "animation",
        "comedy",
        "horror",
        "history",
        "thriller",
    }
    official_youtube = [
        row
        for row in REAL_VIDEO_LIBRARY
        if str(row.get("youtube_video_id") or "").strip()
        and (
            "trailer" in str(row.get("title") or "").lower()
            or str(row.get("category") or "").strip().lower() in movie_like_categories
        )
    ]
    if discovered:
        return [*official_youtube, *discovered]
    return list(official_youtube)


def _generated_template(index: int, *, source_mode: str = "seed") -> dict[str, Any]:
    category_profile = CATEGORY_PROFILES[index % len(CATEGORY_PROFILES)]
    fallback_asset = VIDEO_ASSETS[index % len(VIDEO_ASSETS)]
    library_pool = _combined_real_video_library()
    library = library_pool[index % len(library_pool)] if library_pool else REAL_VIDEO_LIBRARY[index % len(REAL_VIDEO_LIBRARY)]
    language = str(library.get("language") or LANGUAGES[index % len(LANGUAGES)])
    rating = str(library.get("rating") or RATINGS[index % len(RATINGS)])
    year = int(library.get("year") or (2013 + (index % 13)))
    youtube_video_id = str(library.get("youtube_video_id") or "").strip()
    youtube_embed_url = _youtube_embed_url(youtube_video_id)
    explicit_playback = str(library.get("playback_type") or "").strip().lower()
    playback_type = "youtube" if (explicit_playback == "youtube" or youtube_embed_url) else "mp4"

    plan_bucket = index % 10
    if plan_bucket <= 3:
        min_plan = "free"
    elif plan_bucket <= 8:
        min_plan = "basic"
    else:
        min_plan = "premium"

    seed_key = f"{source_mode}-{index}"
    title = str(library.get("title") or f"{category_profile['name']} Feature")
    title_suffix = (index // max(1, len(library_pool))) + 1
    decorated_title = title if title_suffix <= 1 else f"{title} • Cut {title_suffix}"
    fallback_video_url = str(library.get("video_url") or library.get("fallback_video_url") or fallback_asset.get("video_url") or "")
    if playback_type == "youtube" and (not fallback_video_url or "samplelib.com" in fallback_video_url.lower()):
        discovered = _real_video_discovery_pool()
        if discovered:
            fallback_video_url = str(discovered[index % len(discovered)].get("video_url") or fallback_video_url)
    source_tags = [
        *[str(tag).strip().lower() for tag in (library.get("tags") or category_profile["tags"]) if str(tag).strip()],
        "real-video",
        "hybrid-playback",
        language.lower(),
    ][:10]
    source_channel = _derive_source_channel(str(library.get("studio") or category_profile["studios"][index % len(category_profile["studios"])]))
    source_trust_badge = _derive_source_trust_badge(
        title=decorated_title,
        tags=source_tags,
        playback_type=playback_type,
    )
    thumbnail_url = str(library.get("thumbnail_url") or _dynamic_thumbnail_url(seed_key, str(library.get("category") or category_profile["name"]), index % 9))
    source_label = str(library.get("source_label") or ("YouTube Official" if playback_type == "youtube" else "Official Stream"))
    saga_meta = _derive_saga_metadata(decorated_title, str(library.get("category") or category_profile["name"]), str(library.get("studio") or category_profile["studios"][index % len(category_profile["studios"])]), index)
    return {
        "template_id": f"{source_mode}-template-{index:04d}",
        "title": decorated_title,
        "description": str(library.get("description") or "Official trailer or stream from verified public source."),
        "category": str(library.get("category") or category_profile["name"]),
        "duration_seconds": max(60, int(library.get("duration_seconds") or fallback_asset["duration_seconds"])),
        "video_url": fallback_video_url,
        "fallback_video_url": fallback_video_url,
        "playback_type": playback_type,
        "youtube_video_id": youtube_video_id if playback_type == "youtube" else "",
        "youtube_embed_url": youtube_embed_url if playback_type == "youtube" else "",
        "thumbnail_url": thumbnail_url,
        "thumbnail_locked": bool(youtube_video_id),
        "min_plan": min_plan,
        "tags": source_tags,
        "studio": str(library.get("studio") or category_profile["studios"][index % len(category_profile["studios"])]),
        "year": year,
        "language": language,
        "rating": rating,
        "quality_label": "4K" if index % 3 == 0 else "HD",
        "view_count": int(400 + (index * 31) % 92000),
        "like_count": int(60 + (index * 19) % 18000),
        "source_label": source_label,
        "source_trust_badge": source_trust_badge,
        "source_channel": source_channel,
        "saga_key": str(saga_meta.get("saga_key") or "")[:64],
        "saga_name": str(saga_meta.get("saga_name") or "")[:80],
        "saga_order": int(saga_meta.get("saga_order") or 1),
        "spoiler_safe_recap": str(saga_meta.get("spoiler_safe_recap") or "")[:220],
    }


def _build_video_doc(
    template: dict[str, Any],
    *,
    released_at_iso: str,
    drop_key: str,
    batch_id: str,
    source_mode: str,
    sequence_index: int,
) -> dict[str, Any]:
    now_iso = _now_iso()
    video_id = f"wv_{uuid.uuid4().hex[:14]}"
    return {
        "video_id": video_id,
        "id": video_id,
        "source_template_id": str(template.get("template_id") or ""),
        "title": str(template.get("title") or "Watch Video").strip()[:180],
        "description": str(template.get("description") or "").strip()[:1400],
        "category": str(template.get("category") or "General").strip()[:80],
        "duration_seconds": max(0, int(template.get("duration_seconds") or 0)),
        "video_url": str(template.get("video_url") or "").strip(),
        "fallback_video_url": str(template.get("fallback_video_url") or template.get("video_url") or "").strip(),
        "playback_type": str(template.get("playback_type") or "mp4").strip().lower(),
        "youtube_video_id": str(template.get("youtube_video_id") or "").strip(),
        "youtube_embed_url": str(template.get("youtube_embed_url") or "").strip(),
        "thumbnail_url": str(template.get("thumbnail_url") or "").strip(),
        "thumbnail_locked": bool(template.get("thumbnail_locked") or False),
        "source_label": str(template.get("source_label") or "Direct Stream").strip()[:32],
        "source_trust_badge": str(template.get("source_trust_badge") or "Official").strip()[:24],
        "source_channel": str(template.get("source_channel") or template.get("studio") or "Verified Channel").strip()[:64],
        "saga_key": str(template.get("saga_key") or "").strip()[:64],
        "saga_name": str(template.get("saga_name") or "").strip()[:80],
        "saga_order": int(template.get("saga_order") or 1),
        "spoiler_safe_recap": str(template.get("spoiler_safe_recap") or "").strip()[:220],
        "min_plan": str(template.get("min_plan") or "free").strip().lower(),
        "tags": [str(tag).strip() for tag in (template.get("tags") or []) if str(tag).strip()][:10],
        "studio": str(template.get("studio") or "Studio Prime").strip()[:120],
        "year": int(template.get("year") or _now().year),
        "language": str(template.get("language") or "English").strip()[:40],
        "rating": str(template.get("rating") or "PG-13").strip()[:24],
        "quality_label": str(template.get("quality_label") or "HD").strip()[:16],
        "view_count": max(0, int(template.get("view_count") or 0)),
        "like_count": max(0, int(template.get("like_count") or 0)),
        "released_at": released_at_iso,
        "drop_key": drop_key,
        "batch_id": batch_id,
        "is_active": True,
        "source": source_mode,
        "sequence_index": sequence_index,
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def _sanitize_video(
    doc: dict[str, Any],
    *,
    progress_seconds: int = 0,
    completed: bool = False,
    feedback: str = "",
    watchlisted: bool = False,
    recommendation_reason: list[str] | None = None,
    recommendation_score: float | None = None,
    recommendation_signals: list[str] | None = None,
) -> dict[str, Any]:
    safe_score: float | None = None
    if recommendation_score is not None:
        try:
            safe_score = round(max(0.0, min(100.0, float(recommendation_score))), 2)
        except Exception:
            safe_score = None

    return {
        "video_id": str(doc.get("video_id") or ""),
        "title": str(doc.get("title") or ""),
        "description": str(doc.get("description") or ""),
        "category": str(doc.get("category") or "General"),
        "duration_seconds": int(doc.get("duration_seconds") or 0),
        "video_url": str(doc.get("video_url") or ""),
        "fallback_video_url": str(doc.get("fallback_video_url") or doc.get("video_url") or ""),
        "playback_type": str(doc.get("playback_type") or "mp4"),
        "youtube_video_id": str(doc.get("youtube_video_id") or ""),
        "youtube_embed_url": str(doc.get("youtube_embed_url") or ""),
        "source_label": str(doc.get("source_label") or "Direct Stream"),
        "source_trust_badge": str(doc.get("source_trust_badge") or "Official"),
        "source_channel": str(doc.get("source_channel") or doc.get("studio") or "Verified Channel"),
        "saga_key": str(doc.get("saga_key") or ""),
        "saga_name": str(doc.get("saga_name") or ""),
        "saga_order": int(doc.get("saga_order") or 1),
        "spoiler_safe_recap": str(doc.get("spoiler_safe_recap") or ""),
        "thumbnail_url": str(doc.get("thumbnail_url") or ""),
        "min_plan": str(doc.get("min_plan") or "free"),
        "tags": [str(tag) for tag in (doc.get("tags") or []) if str(tag)],
        "studio": str(doc.get("studio") or ""),
        "year": int(doc.get("year") or 0),
        "language": str(doc.get("language") or ""),
        "rating": str(doc.get("rating") or ""),
        "quality_label": str(doc.get("quality_label") or ""),
        "view_count": int(doc.get("view_count") or 0),
        "like_count": int(doc.get("like_count") or 0),
        "drop_key": str(doc.get("drop_key") or ""),
        "released_at": str(doc.get("released_at") or doc.get("created_at") or ""),
        "progress_seconds": int(progress_seconds or 0),
        "completed": bool(completed),
        "feedback": str(feedback or ""),
        "watchlisted": bool(watchlisted),
        "recommendation_reason": [str(x) for x in (recommendation_reason or []) if str(x)],
        "recommendation_score": safe_score,
        "recommendation_signals": [str(x) for x in (recommendation_signals or []) if str(x)][:6],
    }


async def _ensure_feature_registry_entry() -> None:
    existing = await db.feature_registry.find_one({"feature_id": FEATURE_ID}, {"_id": 0, "feature_id": 1})
    if existing:
        return

    now = _now_iso()
    max_order = await db.feature_registry.find_one({}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)])
    next_order = (int(max_order.get("sort_order") or 0) + 1) if max_order else 0
    await db.feature_registry.insert_one(
        {
            "feature_id": FEATURE_ID,
            "title": "Watch Videos",
            "description": "Netflix + YouTube style premium streaming hub with plan-aware access and AI recommendations.",
            "icon": "film",
            "route": FEATURE_ROUTE,
            "category": "productivity",
            "color": "#14B8A6",
            "is_new": True,
            "premium": False,
            "enabled": True,
            "sort_order": next_order,
            "created_at": now,
            "updated_at": now,
        }
    )
    try:
        from routes import feature_registry as feature_registry_route

        feature_registry_route._registry_cache["ts"] = 0
    except Exception as exc:
        logger.warning(f"Watch Videos cache invalidation warning: {exc}")


async def _ensure_catalog_visual_refresh(catalog_coll) -> dict[str, Any]:
    state = await db.system_runtime_flags.find_one({"key": VISUAL_REFRESH_STATE_KEY}, {"_id": 0, "version": 1})
    if state and str(state.get("version") or "") == VISUAL_REFRESH_VERSION:
        return {"status": "already_applied", "version": VISUAL_REFRESH_VERSION}

    await _save_visual_theme_config(await _get_visual_theme_config())
    now_iso = _now_iso()
    applied = await _apply_visual_theme_to_catalog(catalog_coll)

    await db.system_runtime_flags.update_one(
        {"key": VISUAL_REFRESH_STATE_KEY},
        {
            "$set": {
                "key": VISUAL_REFRESH_STATE_KEY,
                "version": VISUAL_REFRESH_VERSION,
                "updated_at": now_iso,
                "updated_count": int(applied.get("updated_count") or 0),
            }
        },
        upsert=True,
    )
    return {
        "status": str(applied.get("status") or "applied"),
        "version": VISUAL_REFRESH_VERSION,
        "updated_count": int(applied.get("updated_count") or 0),
        "theme_cycle": str(applied.get("theme_cycle") or ""),
    }


async def _ensure_seed_catalog() -> dict[str, Any]:
    catalog_coll = db[COLL_CATALOG]
    count = await catalog_coll.count_documents({})
    if count >= SEED_TARGET_COUNT:
        content_refresh = await _ensure_catalog_content_refresh(catalog_coll)
        visual_refresh = await _ensure_catalog_visual_refresh(catalog_coll)
        return {
            "status": "existing",
            "count": count,
            "content_refresh": content_refresh,
            "visual_refresh": visual_refresh,
        }

    inserted_count = 0
    now = _now()
    batch_id = f"seed_{uuid.uuid4().hex[:8]}"
    for idx in range(SEED_TARGET_COUNT):
        template = _generated_template(idx, source_mode="seed")
        days_offset = max(1, (SEED_TARGET_COUNT - idx) // DAILY_DROP_COUNT)
        released_at = (now - timedelta(days=days_offset)).replace(microsecond=0).isoformat()
        doc = _build_video_doc(
            template,
            released_at_iso=released_at,
            drop_key=f"seed-{idx // DAILY_DROP_COUNT:03d}",
            batch_id=batch_id,
            source_mode="seed",
            sequence_index=idx,
        )
        result = await catalog_coll.update_one(
            {"source_template_id": doc["source_template_id"]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        if result.upserted_id:
            inserted_count += 1

    visual_refresh = await _ensure_catalog_visual_refresh(catalog_coll)
    content_refresh = await _ensure_catalog_content_refresh(catalog_coll)
    return {
        "status": "seeded",
        "inserted_count": inserted_count,
        "catalog_count": await catalog_coll.count_documents({}),
        "content_refresh": content_refresh,
        "visual_refresh": visual_refresh,
    }


async def _ensure_catalog_content_refresh(catalog_coll) -> dict[str, Any]:
    state = await db.system_runtime_flags.find_one(
        {"key": CATALOG_CONTENT_STATE_KEY},
        {"_id": 0, "version": 1},
    )
    if state and str(state.get("version") or "") == CATALOG_CONTENT_VERSION:
        return {"status": "already_applied", "version": CATALOG_CONTENT_VERSION}

    rows = await catalog_coll.find(
        {},
        {"_id": 0, "video_id": 1, "sequence_index": 1, "source_template_id": 1, "released_at": 1, "min_plan": 1},
    ).sort("sequence_index", 1).to_list(5000)
    if not rows:
        return {"status": "no_rows", "version": CATALOG_CONTENT_VERSION}

    now_iso = _now_iso()
    updated_count = 0
    for idx, row in enumerate(rows):
        video_id = str(row.get("video_id") or "").strip()
        if not video_id:
            continue

        sequence_index = int(row.get("sequence_index") or idx)
        template = _generated_template(sequence_index, source_mode="seed")
        patch = {
            "source_template_id": str(row.get("source_template_id") or template.get("template_id") or ""),
            "title": str(template.get("title") or "Watch Video").strip()[:180],
            "description": str(template.get("description") or "").strip()[:1400],
            "category": str(template.get("category") or "General").strip()[:80],
            "duration_seconds": max(0, int(template.get("duration_seconds") or 0)),
            "video_url": str(template.get("video_url") or "").strip(),
            "fallback_video_url": str(template.get("fallback_video_url") or template.get("video_url") or "").strip(),
            "playback_type": str(template.get("playback_type") or "mp4").strip().lower(),
            "youtube_video_id": str(template.get("youtube_video_id") or "").strip(),
            "youtube_embed_url": str(template.get("youtube_embed_url") or "").strip(),
            "thumbnail_url": str(template.get("thumbnail_url") or "").strip(),
            "thumbnail_locked": bool(template.get("thumbnail_locked") or False),
            "source_label": str(template.get("source_label") or "Direct Stream").strip()[:32],
            "source_trust_badge": str(template.get("source_trust_badge") or "Official").strip()[:24],
            "source_channel": str(template.get("source_channel") or template.get("studio") or "Verified Channel").strip()[:64],
            "saga_key": str(template.get("saga_key") or "").strip()[:64],
            "saga_name": str(template.get("saga_name") or "").strip()[:80],
            "saga_order": int(template.get("saga_order") or 1),
            "spoiler_safe_recap": str(template.get("spoiler_safe_recap") or "").strip()[:220],
            "tags": [str(tag).strip() for tag in (template.get("tags") or []) if str(tag).strip()][:10],
            "studio": str(template.get("studio") or "Studio Prime").strip()[:120],
            "year": int(template.get("year") or _now().year),
            "language": str(template.get("language") or "English").strip()[:40],
            "rating": str(template.get("rating") or "PG-13").strip()[:24],
            "quality_label": str(template.get("quality_label") or "HD").strip()[:16],
            "min_plan": str(row.get("min_plan") or template.get("min_plan") or "free").strip().lower(),
            "updated_at": now_iso,
        }
        await catalog_coll.update_one({"video_id": video_id}, {"$set": patch})
        updated_count += 1

    await db.system_runtime_flags.update_one(
        {"key": CATALOG_CONTENT_STATE_KEY},
        {
            "$set": {
                "key": CATALOG_CONTENT_STATE_KEY,
                "version": CATALOG_CONTENT_VERSION,
                "updated_at": now_iso,
                "updated_count": int(updated_count),
            },
        },
        upsert=True,
    )
    return {
        "status": "applied",
        "version": CATALOG_CONTENT_VERSION,
        "updated_count": int(updated_count),
    }


async def _quota_snapshot(user: User) -> dict[str, Any]:
    plan = _resolve_plan(user)
    limit = _daily_watch_limit(user, plan)
    used = await db[COLL_WATCH_USAGE].count_documents({"user_id": user.user_id, "day_key": _today_key()})
    return {
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limit": int(limit),
        "used": int(used),
        "remaining": -1 if int(limit) < 0 else max(0, int(limit) - int(used)),
    }


def _catalog_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "video_id": 1,
        "title": 1,
        "description": 1,
        "category": 1,
        "duration_seconds": 1,
        "video_url": 1,
        "fallback_video_url": 1,
        "playback_type": 1,
        "youtube_video_id": 1,
        "youtube_embed_url": 1,
        "source_label": 1,
        "source_trust_badge": 1,
        "source_channel": 1,
        "saga_key": 1,
        "saga_name": 1,
        "saga_order": 1,
        "spoiler_safe_recap": 1,
        "thumbnail_url": 1,
        "min_plan": 1,
        "tags": 1,
        "studio": 1,
        "year": 1,
        "language": 1,
        "rating": 1,
        "quality_label": 1,
        "view_count": 1,
        "like_count": 1,
        "drop_key": 1,
        "released_at": 1,
        "created_at": 1,
    }


def _sort_spec(sort_by: str) -> list[tuple[str, int]]:
    if sort_by == "trending":
        return [("view_count", -1), ("like_count", -1), ("released_at", -1)]
    if sort_by == "duration_desc":
        return [("duration_seconds", -1), ("video_id", 1)]
    if sort_by == "duration_asc":
        return [("duration_seconds", 1), ("video_id", 1)]
    if sort_by == "alphabetical":
        return [("title", 1), ("video_id", 1)]
    return [("released_at", -1)]


async def _fetch_catalog(
    *,
    plan: str,
    query: str = "",
    category: str = "all",
    limit: int = 24,
    offset: int = 0,
    sort_by: str = "latest",
) -> tuple[list[dict[str, Any]], int]:
    filters: dict[str, Any] = _visibility_filter(plan)
    clean_query = str(query or "").strip()
    if clean_query:
        filters["$or"] = [
            {"title": {"$regex": clean_query, "$options": "i"}},
            {"description": {"$regex": clean_query, "$options": "i"}},
            {"tags": {"$regex": clean_query, "$options": "i"}},
            {"studio": {"$regex": clean_query, "$options": "i"}},
        ]

    clean_category = str(category or "all").strip().lower()
    if clean_category and clean_category != "all":
        filters["category"] = {"$regex": f"^{clean_category}$", "$options": "i"}

    safe_limit = min(max(int(limit), 1), 600)
    safe_offset = max(int(offset), 0)
    sort_specs = _sort_spec(str(sort_by or "latest").strip().lower())

    total = await db[COLL_CATALOG].count_documents(filters)
    cursor = db[COLL_CATALOG].find(filters, _catalog_projection()).sort(sort_specs)
    rows = await cursor.skip(safe_offset).limit(safe_limit).to_list(safe_limit)
    return rows, int(total)


async def _feedback_map_for_user(user_id: str) -> dict[str, str]:
    rows = await db[COLL_FEEDBACK].find(
        {"user_id": user_id},
        {"_id": 0, "video_id": 1, "feedback": 1},
    ).to_list(1000)
    return {
        str(row.get("video_id") or ""): str(row.get("feedback") or "")
        for row in rows
        if str(row.get("video_id") or "")
    }


def _default_visual_preferences() -> dict[str, Any]:
    return {
        "show_recommendation_reasons": True,
        "watchlist_sort_mode": "recent",
        "watchlist_sort_direction": "desc",
        "autoplay_next_enabled": True,
    }


def _normalize_visual_preferences(raw: dict[str, Any] | None) -> dict[str, Any]:
    defaults = _default_visual_preferences()
    data = dict(raw or {})
    mode = str(data.get("watchlist_sort_mode") or defaults["watchlist_sort_mode"])
    direction = str(data.get("watchlist_sort_direction") or defaults["watchlist_sort_direction"])

    if mode not in {"recent", "duration", "category"}:
        mode = defaults["watchlist_sort_mode"]
    if direction not in {"asc", "desc"}:
        direction = defaults["watchlist_sort_direction"]

    return {
        "show_recommendation_reasons": bool(data.get("show_recommendation_reasons", defaults["show_recommendation_reasons"])),
        "watchlist_sort_mode": mode,
        "watchlist_sort_direction": direction,
        "autoplay_next_enabled": bool(data.get("autoplay_next_enabled", defaults["autoplay_next_enabled"])),
    }


async def _get_visual_preferences(user_id: str) -> dict[str, Any]:
    row = await db[COLL_PREFS].find_one({"user_id": user_id}, {"_id": 0, "preferences": 1})
    return _normalize_visual_preferences((row or {}).get("preferences") or {})


async def _save_visual_preferences(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    current = await _get_visual_preferences(user_id)
    merged = _normalize_visual_preferences({**current, **patch})
    await db[COLL_PREFS].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "preferences": merged,
                "updated_at": _now_iso(),
            },
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )
    return merged


async def _watchlist_ids_for_user(user_id: str) -> set[str]:
    rows = await db[COLL_WATCHLIST].find(
        {"user_id": user_id},
        {"_id": 0, "video_id": 1},
    ).to_list(2000)
    return {
        str(row.get("video_id") or "")
        for row in rows
        if str(row.get("video_id") or "")
    }


async def _watchlist_videos(
    user_id: str,
    plan: str,
    *,
    feedback_map: dict[str, str],
    limit: int = 24,
    sort_mode: str = "recent",
    sort_dir: str = "desc",
) -> list[dict[str, Any]]:
    rows = await db[COLL_WATCHLIST].find(
        {"user_id": user_id},
        {"_id": 0, "video_id": 1, "updated_at": 1, "added_at": 1},
    ).sort("updated_at", -1).limit(max(1, int(limit)) * 4).to_list(max(1, int(limit)) * 4)

    if not rows:
        return []

    ordered_ids = [str(row.get("video_id") or "") for row in rows if str(row.get("video_id") or "")]
    docs = await db[COLL_CATALOG].find(
        {"video_id": {"$in": ordered_ids}, **_visibility_filter(plan)},
        _catalog_projection(),
    ).to_list(max(80, len(ordered_ids) + 8))
    by_id = {str(doc.get("video_id") or ""): doc for doc in docs}

    merged: list[dict[str, Any]] = []
    for video_id in ordered_ids:
        doc = by_id.get(video_id)
        if not doc:
            continue
        merged.append(
            _sanitize_video(
                doc,
                feedback=feedback_map.get(video_id, ""),
                watchlisted=True,
            )
        )
        if len(merged) >= max(1, int(limit)):
            break

    mode = str(sort_mode or "recent")
    direction = str(sort_dir or "desc")
    if mode == "duration":
        merged.sort(key=lambda row: int(row.get("duration_seconds") or 0), reverse=True)
        if direction == "asc":
            merged.reverse()
    elif mode == "category":
        merged.sort(key=lambda row: f"{str(row.get('category') or '')} {str(row.get('title') or '')}".lower())
        if direction != "asc":
            merged.reverse()
    elif direction == "asc":
        merged.reverse()
    return merged


async def _continue_watching(user_id: str, plan: str, *, feedback_map: dict[str, str], limit: int = 20) -> list[dict[str, Any]]:
    history_rows = await db[COLL_WATCH_HISTORY].find(
        {"user_id": user_id, "completed": {"$ne": True}, "progress_seconds": {"$gt": 0}},
        {"_id": 0, "video_id": 1, "progress_seconds": 1, "completed": 1, "last_watched_at": 1},
    ).sort("last_watched_at", -1).limit(60).to_list(60)

    if not history_rows:
        return []

    ordered_ids = [str(row.get("video_id") or "") for row in history_rows if str(row.get("video_id") or "")]
    id_to_progress = {
        str(row.get("video_id") or ""): {
            "progress_seconds": int(row.get("progress_seconds") or 0),
            "completed": bool(row.get("completed")),
        }
        for row in history_rows
    }
    docs = await db[COLL_CATALOG].find(
        {"video_id": {"$in": ordered_ids}, **_visibility_filter(plan)},
        _catalog_projection(),
    ).to_list(200)
    by_id = {str(doc.get("video_id") or ""): doc for doc in docs}

    merged: list[dict[str, Any]] = []
    for video_id in ordered_ids:
        doc = by_id.get(video_id)
        if not doc:
            continue
        progress_meta = id_to_progress.get(video_id) or {}
        merged.append(
            _sanitize_video(
                doc,
                progress_seconds=int(progress_meta.get("progress_seconds") or 0),
                completed=bool(progress_meta.get("completed")),
                feedback=feedback_map.get(video_id, ""),
            )
        )
        if len(merged) >= limit:
            break
    return merged


async def _build_resume_saga_item(
    user_id: str,
    plan: str,
    *,
    feedback_map: dict[str, str],
    watchlist_ids: set[str],
) -> dict[str, Any] | None:
    history_rows = await db[COLL_WATCH_HISTORY].find(
        {"user_id": user_id, "progress_seconds": {"$gt": 0}},
        {
            "_id": 0,
            "video_id": 1,
            "progress_seconds": 1,
            "completed": 1,
            "last_watched_at": 1,
        },
    ).sort("last_watched_at", -1).limit(120).to_list(120)

    if not history_rows:
        return None

    ordered_ids = [str(row.get("video_id") or "") for row in history_rows if str(row.get("video_id") or "")]
    if not ordered_ids:
        return None

    history_by_id = {
        str(row.get("video_id") or ""): {
            "progress_seconds": int(row.get("progress_seconds") or 0),
            "completed": bool(row.get("completed")),
            "last_watched_at": str(row.get("last_watched_at") or ""),
        }
        for row in history_rows
        if str(row.get("video_id") or "")
    }

    watched_docs = await db[COLL_CATALOG].find(
        {"video_id": {"$in": ordered_ids}, **_visibility_filter(plan)},
        _catalog_projection(),
    ).to_list(240)
    watched_by_id = {str(doc.get("video_id") or ""): doc for doc in watched_docs}

    saga_cache: dict[str, list[dict[str, Any]]] = {}
    for history_row in history_rows:
        current_video_id = str(history_row.get("video_id") or "")
        if not current_video_id:
            continue

        current_doc = watched_by_id.get(current_video_id)
        if not current_doc:
            continue

        saga_key = str(current_doc.get("saga_key") or "").strip()
        if not saga_key:
            continue

        if saga_key not in saga_cache:
            saga_docs = await db[COLL_CATALOG].find(
                {"saga_key": saga_key, **_visibility_filter(plan)},
                _catalog_projection(),
            ).to_list(80)
            saga_cache[saga_key] = sorted(
                saga_docs,
                key=lambda row: (int(row.get("saga_order") or 1), str(row.get("released_at") or "")),
            )

        saga_rows = saga_cache.get(saga_key) or []
        if not saga_rows:
            continue

        current_order = int(current_doc.get("saga_order") or 1)
        history_meta = history_by_id.get(current_video_id) or {}
        current_completed = bool(history_meta.get("completed"))
        target_doc = current_doc

        if current_completed:
            next_doc = next(
                (row for row in saga_rows if int(row.get("saga_order") or 1) > current_order),
                None,
            )
            if next_doc:
                target_doc = next_doc

        target_video_id = str(target_doc.get("video_id") or "")
        target_history = history_by_id.get(target_video_id) or {}
        target_progress = int(target_history.get("progress_seconds") or 0)
        target_completed = bool(target_history.get("completed"))

        resume_video = _sanitize_video(
            target_doc,
            progress_seconds=target_progress,
            completed=target_completed,
            feedback=feedback_map.get(target_video_id, ""),
            watchlisted=target_video_id in watchlist_ids,
        )

        resume_reason = (
            f"Next part unlocked: jump into Part {int(target_doc.get('saga_order') or 1)}."
            if target_video_id != current_video_id
            else "Pick up exactly where you left this saga."
        )

        return {
            "saga_key": saga_key,
            "saga_name": str(target_doc.get("saga_name") or current_doc.get("saga_name") or "Saga Continuity"),
            "resume_video": resume_video,
            "last_watched_video_id": current_video_id,
            "last_watched_at": str(history_meta.get("last_watched_at") or ""),
            "resume_reason": resume_reason,
            "has_next_part": target_video_id != current_video_id,
        }

    return None


async def _build_recommendations(
    user_id: str,
    plan: str,
    *,
    feedback_map: dict[str, str],
    limit: int = 24,
) -> list[dict[str, Any]]:
    history_rows = await db[COLL_WATCH_HISTORY].find(
        {"user_id": user_id},
        {"_id": 0, "video_id": 1, "last_watched_at": 1},
    ).sort("last_watched_at", -1).limit(60).to_list(60)

    watched_ids = [str(row.get("video_id") or "") for row in history_rows if str(row.get("video_id") or "")]
    watched_set = set(watched_ids)
    recent_watch_index: dict[str, int] = {
        video_id: idx
        for idx, video_id in enumerate(watched_ids)
        if video_id
    }

    pref_categories: dict[str, float] = {}
    pref_tags: dict[str, float] = {}
    watchlist_category_affinity: dict[str, float] = {}
    watchlist_tag_affinity: dict[str, float] = {}
    completion_signals: dict[str, float] = {}
    recency_boost_by_category: dict[str, float] = {}

    continue_rows = await _continue_watching(user_id, plan=plan, feedback_map=feedback_map, limit=24)
    continue_ids = {str(row.get("video_id") or "") for row in continue_rows if str(row.get("video_id") or "")}

    watchlist_rows = await _watchlist_videos(
        user_id,
        plan=plan,
        feedback_map=feedback_map,
        limit=40,
        sort_mode="recent",
        sort_dir="desc",
    )
    for row in watchlist_rows:
        category = str(row.get("category") or "").strip().lower()
        if category:
            watchlist_category_affinity[category] = watchlist_category_affinity.get(category, 0.0) + 1.0
        for tag in (row.get("tags") or []):
            clean_tag = str(tag or "").strip().lower()
            if clean_tag:
                watchlist_tag_affinity[clean_tag] = watchlist_tag_affinity.get(clean_tag, 0.0) + 1.0

    if watched_ids:
        watched_docs = await db[COLL_CATALOG].find(
            {"video_id": {"$in": watched_ids}},
            {"_id": 0, "video_id": 1, "category": 1, "tags": 1, "duration_seconds": 1},
        ).to_list(200)
        for doc in watched_docs:
            doc_id = str(doc.get("video_id") or "")
            signal = feedback_map.get(doc_id, "")
            preference_multiplier = 2.0 if signal == "like" else (0.5 if signal == "dislike" else 1.0)
            category = str(doc.get("category") or "").strip().lower()
            if category:
                pref_categories[category] = pref_categories.get(category, 0.0) + preference_multiplier
            for tag in (doc.get("tags") or []):
                clean_tag = str(tag or "").strip().lower()
                if clean_tag:
                    pref_tags[clean_tag] = pref_tags.get(clean_tag, 0.0) + preference_multiplier

            recency_rank = recent_watch_index.get(doc_id)
            if recency_rank is not None and recency_rank < 12 and category:
                recency_boost_by_category[category] = recency_boost_by_category.get(category, 0.0) + max(0.25, (12 - recency_rank) / 12)

            if doc_id in continue_ids:
                duration_hint = max(1.0, min(4.0, float(doc.get("duration_seconds") or 0) / 900.0))
                completion_signals[category] = completion_signals.get(category, 0.0) + duration_hint

    candidate_filter: dict[str, Any] = {**_visibility_filter(plan)}
    if watched_set:
        candidate_filter["video_id"] = {"$nin": list(watched_set)}

    candidates = await db[COLL_CATALOG].find(
        candidate_filter,
        _catalog_projection(),
    ).sort("released_at", -1).limit(180).to_list(180)

    today_key = _today_key()
    scored: list[tuple[float, dict[str, Any], list[str], list[str]]] = []
    category_selection_counter: dict[str, int] = {}
    for doc in candidates:
        video_id = str(doc.get("video_id") or "")
        user_feedback = feedback_map.get(video_id, "")
        if user_feedback == "dislike":
            continue

        category = str(doc.get("category") or "").strip().lower()
        reasons: list[str] = []
        signals: list[str] = []
        score = 1.0 + min(8.0, float(doc.get("view_count") or 0) / 9000.0)
        signals.append("popularity")

        release_time = str(doc.get("released_at") or "")
        try:
            if release_time:
                parsed_release = datetime.fromisoformat(release_time.replace("Z", "+00:00"))
                age_days = max(0.0, (_now() - parsed_release).total_seconds() / 86400.0)
                freshness_boost = max(0.0, 2.4 - (age_days / 21.0))
                score += freshness_boost
                if freshness_boost >= 1.1:
                    reasons.append("Freshly released")
                    signals.append("freshness")
        except Exception:
            pass

        if category:
            category_affinity = float(pref_categories.get(category, 0.0))
            score += category_affinity * 2.6
            if category_affinity >= 1.0:
                reasons.append(f"Matches your {str(doc.get('category') or 'preferred')} history")
                signals.append("history_affinity")

            recency_affinity = float(recency_boost_by_category.get(category, 0.0))
            if recency_affinity > 0:
                score += recency_affinity * 1.35
                if recency_affinity >= 1.0 and len(reasons) < 3:
                    reasons.append("Aligned with your recent watch rhythm")
                    signals.append("recent_behavior")

            completion_affinity = float(completion_signals.get(category, 0.0))
            if completion_affinity > 0:
                score += min(2.8, completion_affinity * 0.5)
                if completion_affinity >= 1.3 and len(reasons) < 3:
                    reasons.append("Improves completion streak odds")
                    signals.append("completion_intent")

            watchlist_affinity = float(watchlist_category_affinity.get(category, 0.0))
            if watchlist_affinity > 0:
                score += min(2.4, watchlist_affinity * 0.8)
                if watchlist_affinity >= 1.0 and len(reasons) < 3:
                    reasons.append("Complements your watchlist")
                    signals.append("watchlist_affinity")

        for tag in (doc.get("tags") or []):
            clean_tag = str(tag or "").strip().lower()
            if clean_tag:
                tag_score = float(pref_tags.get(clean_tag, 0.0))
                score += tag_score * 0.95
                if tag_score >= 1.0 and len(reasons) < 2:
                    reasons.append(f"Based on your interest in {clean_tag}")
                    signals.append("tag_affinity")

                wl_tag_score = float(watchlist_tag_affinity.get(clean_tag, 0.0))
                if wl_tag_score > 0:
                    score += min(1.35, wl_tag_score * 0.45)

        if user_feedback == "like":
            score += 6.0
            reasons.append("You liked similar titles")
            signals.append("feedback_like")
        if str(doc.get("drop_key") or "") == today_key:
            score += 2.2
            if len(reasons) < 2:
                reasons.append("Freshly released today")
            signals.append("daily_drop")

        if category:
            diversity_penalty = max(0, category_selection_counter.get(category, 0) - 2) * 0.7
            if diversity_penalty > 0:
                score -= diversity_penalty
                signals.append("diversity_balance")

        if not reasons:
            reasons.append("Popular among similar viewers")

        scored.append((score, doc, reasons[:3], signals[:6]))
        if category:
            category_selection_counter[category] = category_selection_counter.get(category, 0) + 1

    scored.sort(key=lambda item: (item[0], str(item[1].get("released_at") or "")), reverse=True)
    return [
        _sanitize_video(
            doc,
            feedback=feedback_map.get(str(doc.get("video_id") or ""), ""),
            recommendation_reason=reasons,
            recommendation_score=max(0.0, min(100.0, score * 7.6)),
            recommendation_signals=signals,
        )
        for score, doc, reasons, signals in scored[:max(1, int(limit))]
    ]


async def _build_adaptive_retention_profile(
    user_id: str,
    *,
    plan: str,
    feedback_map: dict[str, str],
    continue_rows: list[dict[str, Any]],
    watchlist_rows: list[dict[str, Any]],
    recommended_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    def _build_streak_rewards_profile(
        rows: list[dict[str, Any]],
        *,
        adaptive_score: int,
        weekly_sessions: int,
    ) -> dict[str, Any]:
        milestones = [
            {"days": 1, "badge_key": "ignite", "badge_title": "Ignite", "reward_label": "+5 queue boost"},
            {"days": 3, "badge_key": "pulse", "badge_title": "Pulse", "reward_label": "Mission hint priority"},
            {"days": 5, "badge_key": "builder", "badge_title": "Builder", "reward_label": "Adaptive score +2"},
            {"days": 7, "badge_key": "surge", "badge_title": "Surge", "reward_label": "Smart-next turbo slot"},
            {"days": 14, "badge_key": "marathon", "badge_title": "Marathon", "reward_label": "Retention shield"},
            {"days": 21, "badge_key": "elite", "badge_title": "Elite", "reward_label": "Priority recommendation mix"},
            {"days": 30, "badge_key": "legend", "badge_title": "Legend", "reward_label": "Streak hall of fame"},
        ]

        watched_days: set[datetime.date] = set()
        for row in rows or []:
            raw = str(row.get("last_watched_at") or "")
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                continue
            watched_days.add(parsed.astimezone(timezone.utc).date())

        if not watched_days:
            return {
                "current_streak_days": 0,
                "total_watch_days": 0,
                "streak_status": "cold",
                "points": 0,
                "current_badge": "Not unlocked",
                "badges_unlocked": [],
                "next_milestone": {
                    "required_days": 1,
                    "badge_title": "Ignite",
                    "reward_label": "+5 queue boost",
                    "remaining_days": 1,
                    "progress_pct": 0,
                },
            }

        today = _now().date()
        latest_day = max(watched_days)
        streak_anchor = today if today in watched_days else latest_day

        streak_days = 0
        cursor = streak_anchor
        while cursor in watched_days:
            streak_days += 1
            cursor = cursor - timedelta(days=1)

        days_since_last = max(0, (today - latest_day).days)
        streak_status = "active" if days_since_last == 0 else ("at_risk" if days_since_last == 1 else "cold")
        points = int(max(0, min(5000, (streak_days * 22) + int(adaptive_score * 1.8) + (weekly_sessions * 6))))

        unlocked = [m for m in milestones if streak_days >= int(m["days"])]
        current_badge = unlocked[-1]["badge_title"] if unlocked else "Not unlocked"
        badges_unlocked = [
            {
                "badge_key": str(item["badge_key"]),
                "badge_title": str(item["badge_title"]),
                "reward_label": str(item["reward_label"]),
                "required_days": int(item["days"]),
            }
            for item in unlocked[-4:]
        ]

        next_milestone = next((m for m in milestones if streak_days < int(m["days"])), None)
        if next_milestone:
            prev_days = int(unlocked[-1]["days"]) if unlocked else 0
            span = max(1, int(next_milestone["days"]) - prev_days)
            progress = int(round(max(0.0, min(100.0, ((streak_days - prev_days) / span) * 100.0))))
            next_payload = {
                "required_days": int(next_milestone["days"]),
                "badge_title": str(next_milestone["badge_title"]),
                "reward_label": str(next_milestone["reward_label"]),
                "remaining_days": max(0, int(next_milestone["days"]) - streak_days),
                "progress_pct": progress,
            }
        else:
            next_payload = {
                "required_days": streak_days,
                "badge_title": current_badge,
                "reward_label": "All milestone rewards unlocked",
                "remaining_days": 0,
                "progress_pct": 100,
            }

        return {
            "current_streak_days": int(streak_days),
            "total_watch_days": int(len(watched_days)),
            "streak_status": streak_status,
            "points": points,
            "current_badge": current_badge,
            "badges_unlocked": badges_unlocked,
            "next_milestone": next_payload,
        }

    history_rows = await db[COLL_WATCH_HISTORY].find(
        {"user_id": user_id},
        {
            "_id": 0,
            "progress_seconds": 1,
            "completed": 1,
            "completion_ratio": 1,
            "last_watched_at": 1,
        },
    ).sort("last_watched_at", -1).limit(80).to_list(80)

    recommendation_quality_avg = (
        sum(float(row.get("recommendation_score") or 0) for row in (recommended_rows or [])[:12])
        / max(1, min(12, len(recommended_rows or [])))
    ) if recommended_rows else 0.0

    empty_streak_rewards = _build_streak_rewards_profile([], adaptive_score=24, weekly_sessions=0)

    if not history_rows:
        return {
            "score": 24,
            "level": "Warm-up",
            "churn_risk": "medium",
            "mission_focus": "kickoff_watchlist",
            "risk_pct": 58,
            "adaptive_signals": {
                "watch_sessions_7d": 0,
                "completion_rate_recent_pct": 0,
                "likes_ratio_pct": 0,
                "continue_queue_depth": len(continue_rows),
                "watchlist_depth": len(watchlist_rows),
                "recommendation_quality_avg": round(recommendation_quality_avg, 2),
            },
            "next_best_actions": [
                "Start one watchlist title to seed better recommendations",
                "Complete at least one video today for stronger momentum",
            ],
            "streak_rewards": empty_streak_rewards,
        }

    now = _now()
    recent_7d = 0
    completed_recent = 0
    completion_samples = 0
    recency_factor_sum = 0.0
    for row in history_rows:
        watched_at_raw = str(row.get("last_watched_at") or "")
        parsed = None
        try:
            if watched_at_raw:
                parsed = datetime.fromisoformat(watched_at_raw.replace("Z", "+00:00"))
        except Exception:
            parsed = None

        if parsed:
            age_days = max(0.0, (now - parsed).total_seconds() / 86400.0)
            if age_days <= 7.0:
                recent_7d += 1
            recency_factor_sum += max(0.0, 1.0 - min(age_days, 21.0) / 21.0)

        completion_ratio = float(row.get("completion_ratio") or 0.0)
        completion_flag = bool(row.get("completed")) or completion_ratio >= 0.98
        completion_samples += 1
        if completion_flag:
            completed_recent += 1

    likes = sum(1 for value in (feedback_map or {}).values() if str(value) == "like")
    dislikes = sum(1 for value in (feedback_map or {}).values() if str(value) == "dislike")
    feedback_total = max(1, likes + dislikes)
    likes_ratio = likes / feedback_total

    completion_rate = completed_recent / max(1, completion_samples)
    normalized_recency = recency_factor_sum / max(1, len(history_rows))
    queue_depth = len(continue_rows)
    watchlist_depth = len(watchlist_rows)

    score_raw = (
        min(35.0, recent_7d * 4.2)
        + min(25.0, completion_rate * 25.0)
        + min(14.0, likes_ratio * 14.0)
        + min(10.0, normalized_recency * 10.0)
        + min(8.0, queue_depth * 1.6)
        + min(8.0, watchlist_depth * 0.9)
    )
    score = int(round(max(0.0, min(100.0, score_raw))))

    risk_raw = (
        100.0
        - (score * 0.72)
        - min(16.0, recommendation_quality_avg * 0.17)
        + (12.0 if queue_depth == 0 else 0.0)
        + (6.0 if watchlist_depth == 0 else 0.0)
    )
    risk_pct = int(round(max(5.0, min(95.0, risk_raw))))

    if score >= 78:
        level = "Unstoppable"
    elif score >= 54:
        level = "Hot streak"
    elif score >= 34:
        level = "Building"
    else:
        level = "Warm-up"

    if risk_pct >= 65:
        churn_risk = "high"
    elif risk_pct >= 40:
        churn_risk = "medium"
    else:
        churn_risk = "low"

    mission_focus = "continue_queue"
    if watchlist_depth >= 3 and queue_depth <= 1:
        mission_focus = "watchlist_to_play"
    elif completion_rate < 0.35:
        mission_focus = "finish_in_progress"
    elif recommendation_quality_avg < 45:
        mission_focus = "feedback_tune"
    elif recent_7d <= 1:
        mission_focus = "daily_return"

    next_best_actions: list[str] = []
    if mission_focus == "finish_in_progress":
        next_best_actions.append("Finish one in-progress title to raise recommendation confidence")
    if mission_focus == "watchlist_to_play":
        next_best_actions.append("Play your top watchlist pick to avoid queue decay")
    if mission_focus == "feedback_tune":
        next_best_actions.append("Like/dislike 2 titles so ranking adapts faster")
    if mission_focus == "daily_return":
        next_best_actions.append("Watch one short title today to keep your streak active")
    if not next_best_actions:
        next_best_actions.append("Continue your queue now to protect your momentum")
    if queue_depth == 0:
        next_best_actions.append("Start a fresh title to rebuild your continue queue")

    streak_rewards = _build_streak_rewards_profile(
        history_rows,
        adaptive_score=score,
        weekly_sessions=recent_7d,
    )

    return {
        "score": score,
        "level": level,
        "churn_risk": churn_risk,
        "mission_focus": mission_focus,
        "risk_pct": risk_pct,
        "adaptive_signals": {
            "watch_sessions_7d": recent_7d,
            "completion_rate_recent_pct": round(completion_rate * 100.0, 2),
            "likes_ratio_pct": round(likes_ratio * 100.0, 2),
            "continue_queue_depth": queue_depth,
            "watchlist_depth": watchlist_depth,
            "recommendation_quality_avg": round(recommendation_quality_avg, 2),
        },
        "next_best_actions": next_best_actions[:4],
        "streak_rewards": streak_rewards,
    }


def _fallback_queue_insight(*, watchlist_count: int, continue_count: int, plan: str) -> dict[str, str]:
    if watchlist_count > 0 and continue_count > 0:
        return {
            "headline": f"Queue ready: {watchlist_count} saved, {continue_count} in progress",
            "reason": "Jump back in where you left off or continue from your saved shortlist.",
            "source": "deterministic",
        }
    if watchlist_count > 0:
        return {
            "headline": f"Your watchlist has {watchlist_count} ready picks",
            "reason": "Your saved titles are ready to play instantly.",
            "source": "deterministic",
        }
    if continue_count > 0:
        return {
            "headline": f"Resume your queue ({continue_count} in progress)",
            "reason": "Continue from your latest progress with one click.",
            "source": "deterministic",
        }
    return {
        "headline": f"{plan.capitalize()} feed ready",
        "reason": "Browse new drops and start building your personal queue.",
        "source": "deterministic",
    }


async def _build_queue_insight(
    user: User,
    *,
    watchlist_rows: list[dict[str, Any]],
    continue_rows: list[dict[str, Any]],
    recommended_rows: list[dict[str, Any]],
) -> dict[str, str]:
    plan = _resolve_plan(user)
    fallback = _fallback_queue_insight(
        watchlist_count=len(watchlist_rows),
        continue_count=len(continue_rows),
        plan=plan,
    )

    if not EMERGENT_LLM_KEY:
        return fallback

    queue_titles = [
        str(row.get("title") or "")
        for row in ([*watchlist_rows[:3], *continue_rows[:2], *recommended_rows[:2]])
        if str(row.get("title") or "")
    ]
    if not queue_titles:
        return fallback

    prompt = (
        "Return strict JSON only with keys: headline, reason. "
        "Keep headline <= 70 chars and reason <= 120 chars. "
        f"User plan: {plan}. Queue titles: {queue_titles}."
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"wv-queue-{user.user_id}-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You are a streaming concierge."
                " Generate concise, motivating queue copy."
                " Return JSON only."
            ),
        ).with_model("openai", "gpt-5.2")

        response = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=8.0)
        text = response.text if hasattr(response, "text") else str(response)
        clean = str(text or "").strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]

        parsed = json.loads(clean.strip())
        headline = str(parsed.get("headline") or "").strip()[:70]
        reason = str(parsed.get("reason") or "").strip()[:120]
        if not headline:
            return fallback

        return {
            "headline": headline,
            "reason": reason or fallback["reason"],
            "source": "llm:gpt-5.2",
        }
    except Exception as exc:
        logger.warning(f"Watch Videos queue insight fallback: {exc}")
        return fallback


def _chunk_rows(rows: list[dict[str, Any]], chunk_size: int = 1000) -> list[list[dict[str, Any]]]:
    return [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]


async def _active_entitled_users() -> list[dict[str, Any]]:
    rows = await db.users.find(
        {
            "access_locked": {"$ne": True},
            "$or": [
                {"subscription_status": "active"},
                {"subscription_permanent": True},
                {"full_access": True},
                {"is_admin": True},
            ],
        },
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "full_name": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "is_admin": 1,
            "full_access": 1,
        },
    ).to_list(120000)

    users: list[dict[str, Any]] = []
    for row in rows:
        user_id = str(row.get("user_id") or "").strip()
        email = str(row.get("email") or "").strip()
        if not user_id or not email:
            continue
        users.append(row)
    return users


async def _emit_new_video_notifications(users: list[dict[str, Any]], videos: list[dict[str, Any]]) -> int:
    if not users or not videos:
        return 0

    now_iso = _now_iso()
    count_label = len(videos)
    titles = ", ".join([str(v.get("title") or "") for v in videos][:3])
    docs: list[dict[str, Any]] = []
    for user in users:
        user_id = str(user.get("user_id") or "")
        if not user_id:
            continue
        notification_id = f"notif_{uuid.uuid4().hex[:12]}"
        docs.append(
            {
                "notification_id": notification_id,
                "id": notification_id,
                "user_id": user_id,
                "type": "watch_videos_new_release",
                "title": f"{count_label} new videos are now live",
                "message": f"Today's Watch Videos drop: {titles}",
                "action_url": "/features/watch-videos?source=daily-drop",
                "read": False,
                "created_at": now_iso,
                "meta": {
                    "feature_id": FEATURE_ID,
                    "drop_key": _today_key(),
                    "video_ids": [str(v.get("video_id") or "") for v in videos],
                },
            }
        )

    for batch in _chunk_rows(docs, 1000):
        if batch:
            await db.notifications.insert_many(batch)
    return len(docs)


async def _send_new_video_emails(users: list[dict[str, Any]], videos: list[dict[str, Any]]) -> dict[str, Any]:
    if not users or not videos:
        return {"attempted": 0, "sent": 0, "failed": 0}

    count_label = len(videos)
    title_line = " • ".join([str(v.get("title") or "") for v in videos][:4])
    semaphore = asyncio.Semaphore(20)
    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

    video_ids = sorted(str(v.get("video_id") or v.get("id") or "") for v in videos if str(v.get("video_id") or v.get("id") or ""))
    drop_hash = hashlib.sha256("|".join(video_ids).encode("utf-8", errors="ignore")).hexdigest()[:16] if video_ids else _today_key()

    async def _send_one(user: dict[str, Any]) -> bool:
        user_id = str(user.get("user_id") or "")
        email = str(user.get("email") or "").strip()
        if not user_id or not email:
            return False
        email_normalized = email.lower()
        dedupe_key = f"watch-videos-drop:{drop_hash}:{email_normalized}"
        try:
            async with semaphore:
                reserved = await reserve_dispatch_once(
                    dedupe_key=dedupe_key,
                    event_type="watch_videos_drop",
                    channel="email",
                    recipient=email_normalized,
                    payload={"drop_hash": drop_hash, "video_count": count_label},
                )
                if not reserved:
                    return False

                result = await notify.reminder(
                    user_id=user_id,
                    email=email,
                    name=str(user.get("full_name") or user.get("name") or "there").strip() or "there",
                    title=f"{count_label} new videos are now live in Watch Videos",
                    time_str=_now().strftime("%b %d, %Y %H:%M UTC"),
                    reminder_type="watch_videos",
                    details=(
                        f"Fresh drop now streaming: {title_line}. "
                        "Open Watch Videos to continue your personalized feed."
                    ).strip(),
                    dedupe_key=dedupe_key,
                )
            ok = bool(result.get("success"))
            await mark_dispatch_status(
                dedupe_key=dedupe_key,
                status="sent" if ok else "failed",
                extra={"sent_at": _now_iso(), "flow": "watch_videos_drop"} if ok else {"error": str(result.get("error") or "send_failed")[:300]},
            )
            return ok
        except Exception:
            try:
                await mark_dispatch_status(
                    dedupe_key=dedupe_key,
                    status="failed",
                    extra={"error": "exception"},
                )
            except Exception:
                pass
            return False

    results = await asyncio.gather(*[_send_one(user) for user in users], return_exceptions=True)
    sent = 0
    failed = 0
    for result in results:
        if isinstance(result, Exception):
            failed += 1
            continue
        if result:
            sent += 1
        else:
            failed += 1
    return {"attempted": len(users), "sent": sent, "failed": failed}


watch_videos_catalog_service = WatchVideosCatalogService(
    fetch_catalog=_fetch_catalog,
    sanitize_video=_sanitize_video,
    watchlist_ids_for_user=_watchlist_ids_for_user,
    feedback_map_for_user=_feedback_map_for_user,
)

watch_videos_recommendation_service = WatchVideosRecommendationService(
    build_recommendations=_build_recommendations,
    feedback_map_for_user=_feedback_map_for_user,
)

watch_videos_playback_service = WatchVideosPlaybackService(
    quota_snapshot=_quota_snapshot,
    daily_watch_limit=_daily_watch_limit,
    today_key=_today_key,
    now_iso=_now_iso,
    sanitize_video=_sanitize_video,
    catalog_projection=_catalog_projection,
    resolve_plan=_resolve_plan,
    visibility_filter=_visibility_filter,
    db=db,
    coll_catalog=COLL_CATALOG,
    coll_watch_usage=COLL_WATCH_USAGE,
    coll_watch_history=COLL_WATCH_HISTORY,
    coll_feedback=COLL_FEEDBACK,
    coll_watchlist=COLL_WATCHLIST,
)


async def run_watch_videos_daily_drop(
    *,
    triggered_by: str = "scheduler:daily",
    force: bool = False,
) -> dict[str, Any]:
    await _ensure_seed_catalog()
    await _ensure_feature_registry_entry()

    day_key = _today_key()
    run_id = f"wv_drop_{uuid.uuid4().hex[:10]}"
    now_iso = _now_iso()

    state_doc = await db.system_runtime_flags.find_one({"key": STATE_FLAG_KEY}, {"_id": 0, "value": 1}) or {}
    state_value = state_doc.get("value") if isinstance(state_doc.get("value"), dict) else {}
    if not force and str(state_value.get("last_success_day") or "") == day_key:
        return {
            "status": "skipped",
            "reason": "already_completed_today",
            "day_key": day_key,
            "run_id": run_id,
            "triggered_by": triggered_by,
        }

    next_index = int(state_value.get("next_index") or 0)
    batch_id = f"drop_{day_key}_{uuid.uuid4().hex[:6]}"

    inserted_docs: list[dict[str, Any]] = []
    for position in range(DAILY_DROP_COUNT):
        source_idx = (next_index + position) % SEED_TARGET_COUNT
        template = _generated_template(source_idx, source_mode="daily")
        template["template_id"] = f"daily-template-{day_key}-{source_idx:04d}-{position:02d}"
        doc = _build_video_doc(
            template,
            released_at_iso=now_iso,
            drop_key=day_key,
            batch_id=batch_id,
            source_mode="daily_drop",
            sequence_index=position,
        )
        await db[COLL_CATALOG].insert_one(doc)
        inserted_docs.append(doc)

    theme_apply = await _apply_visual_theme_to_catalog(
        db[COLL_CATALOG],
        video_ids=[str(doc.get("video_id") or "") for doc in inserted_docs],
    )

    await db.system_runtime_flags.update_one(
        {"key": STATE_FLAG_KEY},
        {
            "$set": {
                "key": STATE_FLAG_KEY,
                "value": {
                    "last_success_day": day_key,
                    "next_index": (next_index + DAILY_DROP_COUNT) % SEED_TARGET_COUNT,
                    "last_run_id": run_id,
                    "last_triggered_by": triggered_by,
                    "last_inserted_video_ids": [doc.get("video_id") for doc in inserted_docs],
                    "updated_at": now_iso,
                },
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    users = await _active_entitled_users()
    in_app_count = await _emit_new_video_notifications(users, inserted_docs)
    email_summary = await _send_new_video_emails(users, inserted_docs)

    summary = {
        "status": "ok",
        "run_id": run_id,
        "day_key": day_key,
        "triggered_by": triggered_by,
        "inserted_count": len(inserted_docs),
        "inserted_video_ids": [doc.get("video_id") for doc in inserted_docs],
        "theme_apply": theme_apply,
        "in_app_notified": int(in_app_count),
        "email": email_summary,
    }
    await db[COLL_INGEST_RUNS].insert_one(
        {
            "run_id": run_id,
            "feature_id": FEATURE_ID,
            "day_key": day_key,
            "triggered_by": triggered_by,
            "summary": summary,
            "created_at": now_iso,
        }
    )
    return summary


@router.get("/bootstrap")
async def watch_videos_bootstrap(request: Request):
    user = await require_auth(request)
    await _ensure_seed_catalog()
    await _ensure_feature_registry_entry()

    quota = await _quota_snapshot(user)
    plan = str(quota.get("plan") or "free")
    role = resolve_user_role(user)
    can_admin_visuals = role in {"admin", "super_admin", "ops_admin"}
    visual_preferences = await _get_visual_preferences(user.user_id)
    feedback_map = await _feedback_map_for_user(user.user_id)
    watchlist_rows = await _watchlist_videos(
        user.user_id,
        plan=plan,
        feedback_map=feedback_map,
        limit=24,
        sort_mode=str(visual_preferences.get("watchlist_sort_mode") or "recent"),
        sort_dir=str(visual_preferences.get("watchlist_sort_direction") or "desc"),
    )
    watchlist_ids = {str(row.get("video_id") or "") for row in watchlist_rows if str(row.get("video_id") or "")}

    all_rows, total_visible = await _fetch_catalog(plan=plan, limit=520, offset=0, sort_by="latest")
    trending_rows, _ = await _fetch_catalog(plan=plan, limit=28, offset=0, sort_by="trending")
    new_rows, _ = await _fetch_catalog(plan=plan, limit=28, offset=0, sort_by="latest")

    continue_rows = await _continue_watching(user.user_id, plan=plan, feedback_map=feedback_map, limit=20)
    recommended_rows = await _build_recommendations(user.user_id, plan=plan, feedback_map=feedback_map, limit=24)
    retention_profile = await _build_adaptive_retention_profile(
        user.user_id,
        plan=plan,
        feedback_map=feedback_map,
        continue_rows=continue_rows,
        watchlist_rows=watchlist_rows,
        recommended_rows=recommended_rows,
    )
    saga_resume_item = await _build_resume_saga_item(
        user.user_id,
        plan=plan,
        feedback_map=feedback_map,
        watchlist_ids=watchlist_ids,
    )

    def _mark_watchlisted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**row, "watchlisted": str(row.get("video_id") or "") in watchlist_ids} for row in rows]

    continue_rows = _mark_watchlisted(continue_rows)
    recommended_rows = _mark_watchlisted(recommended_rows)

    today_drop = [
        _sanitize_video(
            row,
            feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
            watchlisted=str(row.get("video_id") or "") in watchlist_ids,
        )
        for row in new_rows
        if str(row.get("drop_key") or "") == _today_key()
    ][:10]
    if not today_drop:
        today_drop = [
            _sanitize_video(
                row,
                feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
                watchlisted=str(row.get("video_id") or "") in watchlist_ids,
            )
            for row in new_rows[:DAILY_DROP_COUNT]
        ]

    continue_ids = {str(row.get("video_id") or "") for row in continue_rows}
    catalog = [
        _sanitize_video(
            row,
            feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
            watchlisted=str(row.get("video_id") or "") in watchlist_ids,
        )
        for row in all_rows
        if str(row.get("video_id") or "") not in continue_ids
    ]

    categories = sorted({str(row.get("category") or "General") for row in all_rows})
    category_rows: dict[str, list[dict[str, Any]]] = {}
    for category in categories[:MAX_CATEGORY_ROWS]:
        cat_rows, _ = await _fetch_catalog(plan=plan, category=category, limit=12, sort_by="trending")
        category_rows[category] = [
            _sanitize_video(
                row,
                feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
                watchlisted=str(row.get("video_id") or "") in watchlist_ids,
            )
            for row in cat_rows
        ]

    featured_video = (
        recommended_rows[0]
        if recommended_rows
        else (
            _sanitize_video(
                trending_rows[0],
                feedback=feedback_map.get(str(trending_rows[0].get("video_id") or ""), ""),
                watchlisted=str(trending_rows[0].get("video_id") or "") in watchlist_ids,
            )
            if trending_rows
            else None
        )
    )
    selected_video = continue_rows[0] if continue_rows else (featured_video or (catalog[0] if catalog else None))
    queue_insight = await _build_queue_insight(
        user,
        watchlist_rows=watchlist_rows,
        continue_rows=continue_rows,
        recommended_rows=recommended_rows,
    )

    return {
        "plan": plan,
        "scope_label": str(quota.get("scope_label") or _scope_label(plan)),
        "quota": quota,
        "total_visible": int(total_visible),
        "total_catalog": int(await db[COLL_CATALOG].count_documents({"is_active": {"$ne": False}})),
        "categories": categories,
        "featured_video": featured_video,
        "today_drop": today_drop,
        "continue_watching": continue_rows,
        "continue_queue": continue_rows[:12],
        "saga_resume_item": saga_resume_item,
        "watchlist": watchlist_rows,
        "retention_profile": retention_profile,
        "queue_shortcuts": {
            "watchlist_count": len(watchlist_rows),
            "continue_count": len(continue_rows),
            "watchlist_first_video_id": str(watchlist_rows[0].get("video_id") or "") if watchlist_rows else "",
            "continue_first_video_id": str(continue_rows[0].get("video_id") or "") if continue_rows else "",
            "queue_insight": queue_insight,
        },
        "visual_preferences": visual_preferences,
        "can_admin_visuals": can_admin_visuals,
        "visual_theme": (await _get_visual_theme_config()) if can_admin_visuals else None,
        "recommended_for_you": recommended_rows,
        "trending_now": [
            _sanitize_video(
                row,
                feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
                watchlisted=str(row.get("video_id") or "") in watchlist_ids,
            )
            for row in trending_rows
        ],
        "new_releases": [
            _sanitize_video(
                row,
                feedback=feedback_map.get(str(row.get("video_id") or ""), ""),
                watchlisted=str(row.get("video_id") or "") in watchlist_ids,
            )
            for row in new_rows
        ],
        "category_rows": category_rows,
        "feedback_by_video": feedback_map,
        "catalog": catalog,
        "selected_video": selected_video,
        "generated_at": _now_iso(),
    }


@router.get("/health")
async def watch_videos_health(request: Request):
    """Stable health endpoint for frontend/E2E contract checks."""
    user = await require_auth(request)
    plan = _resolve_plan(user)
    await _ensure_seed_catalog()
    return {
        "status": "healthy",
        "feature_id": FEATURE_ID,
        "feature_route": FEATURE_ROUTE,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "generated_at": _now_iso(),
    }


@router.get("/recommendations/reasons")
async def watch_videos_recommendation_reasons(request: Request, limit: int = Query(default=20, ge=1, le=80)):
    """Explicit recommendations reasons endpoint to prevent frontend contract drift."""
    user = await require_auth(request)
    await _ensure_seed_catalog()

    plan = _resolve_plan(user)
    reason_payload = await watch_videos_recommendation_service.recommendation_reasons(
        user_id=user.user_id,
        plan=plan,
        limit=max(1, int(limit)),
    )
    return {
        "success": True,
        "feature_id": FEATURE_ID,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "count": int(reason_payload.get("count") or 0),
        "items": reason_payload.get("items") or [],
        "generated_at": _now_iso(),
    }


@router.get("/catalog")
async def watch_videos_catalog(
    request: Request,
    query: str = Query(default="", max_length=120),
    category: str = Query(default="all", max_length=60),
    sort_by: str = Query(default="latest", pattern="^(latest|trending|duration_desc|duration_asc|alphabetical)$"),
    limit: int = Query(default=60, ge=1, le=600),
    offset: int = Query(default=0, ge=0),
):
    user = await require_auth(request)
    await _ensure_seed_catalog()

    quota = await _quota_snapshot(user)
    plan = str(quota.get("plan") or "free")
    catalog_payload = await watch_videos_catalog_service.catalog_response(
        user_id=user.user_id,
        plan=plan,
        query=query,
        category=category,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )

    return {
        "plan": plan,
        "scope_label": str(quota.get("scope_label") or _scope_label(plan)),
        "quota": quota,
        "query": str(query or "").strip(),
        "category": str(category or "all").strip(),
        "sort_by": sort_by,
        "total": int(catalog_payload.get("total") or 0),
        "offset": int(offset),
        "limit": int(limit),
        "has_more": bool(catalog_payload.get("has_more")),
        "items": catalog_payload.get("items") or [],
    }


@router.post("/watch")
async def watch_videos_track_watch(payload: WatchEventRequest, request: Request):
    started_at = _now()
    source_tag = str(payload.source or "player")[:40]
    user = await require_auth(request)
    await _ensure_seed_catalog()

    plan = _resolve_plan(user)
    try:
        video_doc = await db[COLL_CATALOG].find_one(
            {"video_id": payload.video_id, **_visibility_filter(plan)},
            _catalog_projection(),
        )
        if not video_doc:
            exists = await db[COLL_CATALOG].find_one({"video_id": payload.video_id}, {"_id": 0, "video_id": 1})
            if exists:
                raise HTTPException(status_code=403, detail="This video requires a higher subscription plan.")
            raise HTTPException(status_code=404, detail="Video not found")

        playback_payload = await watch_videos_playback_service.track_watch(user=user, payload=payload)
        if playback_payload.get("success") is not True and playback_payload.get("error") == "daily_watch_cap_reached":
            quota = playback_payload.get("quota") or {}
            raise HTTPException(
                status_code=429,
                detail=(
                    f"{quota.get('scope_label')}: daily watch cap reached "
                    f"({int(quota.get('limit') or 0)} videos/day). Upgrade to continue watching more titles."
                ),
            )

        feedback_map = await _feedback_map_for_user(user.user_id)
        watchlist_ids = await _watchlist_ids_for_user(user.user_id)
        progress_seconds = int((playback_payload.get("history") or {}).get("progress_seconds") or 0)
        completed = bool((playback_payload.get("history") or {}).get("completed"))
        response_payload = {
            "success": True,
            "video_id": payload.video_id,
            "plan": str((playback_payload.get("quota") or {}).get("plan") or plan),
            "scope_label": str((playback_payload.get("quota") or {}).get("scope_label") or _scope_label(plan)),
            "quota": playback_payload.get("quota") or {},
            "history": playback_payload.get("history") or {},
            "video": _sanitize_video(
                video_doc,
                progress_seconds=progress_seconds,
                completed=completed,
                feedback=feedback_map.get(payload.video_id, ""),
                watchlisted=payload.video_id in watchlist_ids,
            ),
        }
        await _record_api_observability(
            endpoint="watch",
            user_id=user.user_id,
            plan=plan,
            status_code=200,
            duration_ms=_elapsed_ms(started_at),
            source=source_tag,
        )
        return response_payload
    except HTTPException as http_exc:
        await _record_api_observability(
            endpoint="watch",
            user_id=user.user_id,
            plan=plan,
            status_code=http_exc.status_code,
            duration_ms=_elapsed_ms(started_at),
            source=source_tag,
            error_code=str(http_exc.detail or "")[:160],
        )
        raise
    except Exception as exc:
        await _record_api_observability(
            endpoint="watch",
            user_id=user.user_id,
            plan=plan,
            status_code=500,
            duration_ms=_elapsed_ms(started_at),
            source=source_tag,
            error_code=type(exc).__name__,
        )
        raise


@router.post("/feedback")
async def watch_videos_feedback(payload: VideoFeedbackRequest, request: Request):
    started_at = _now()
    user = await require_auth(request)
    await _ensure_seed_catalog()

    plan = _resolve_plan(user)
    try:
        exists = await db[COLL_CATALOG].find_one(
            {"video_id": payload.video_id, **_visibility_filter(plan)},
            {"_id": 0, "video_id": 1},
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Video unavailable for feedback")

        feedback_state = await watch_videos_playback_service.set_feedback(user=user, payload=payload)

        feedback_map = await _feedback_map_for_user(user.user_id)
        response_payload = {
            "success": bool(feedback_state.get("success")),
            "video_id": payload.video_id,
            "feedback": payload.feedback,
            "updated_at": _now_iso(),
            "feedback_by_video": feedback_map,
            "recommended_for_you": await _build_recommendations(user.user_id, plan=plan, feedback_map=feedback_map, limit=24),
        }
        await _record_api_observability(
            endpoint="feedback",
            user_id=user.user_id,
            plan=plan,
            status_code=200,
            duration_ms=_elapsed_ms(started_at),
            source=str(payload.feedback or "")[:24],
        )
        return response_payload
    except HTTPException as http_exc:
        await _record_api_observability(
            endpoint="feedback",
            user_id=user.user_id,
            plan=plan,
            status_code=http_exc.status_code,
            duration_ms=_elapsed_ms(started_at),
            source=str(payload.feedback or "")[:24],
            error_code=str(http_exc.detail or "")[:160],
        )
        raise
    except Exception as exc:
        await _record_api_observability(
            endpoint="feedback",
            user_id=user.user_id,
            plan=plan,
            status_code=500,
            duration_ms=_elapsed_ms(started_at),
            source=str(payload.feedback or "")[:24],
            error_code=type(exc).__name__,
        )
        raise


@router.get("/preferences")
async def watch_videos_preferences(request: Request):
    user = await require_auth(request)
    return {
        "success": True,
        "preferences": await _get_visual_preferences(user.user_id),
    }


@router.post("/preferences")
async def watch_videos_preferences_update(payload: VideoVisualPreferencesUpdateRequest, request: Request):
    user = await require_auth(request)
    patch = {
        key: value
        for key, value in {
            "show_recommendation_reasons": payload.show_recommendation_reasons,
            "watchlist_sort_mode": payload.watchlist_sort_mode,
            "watchlist_sort_direction": payload.watchlist_sort_direction,
            "autoplay_next_enabled": payload.autoplay_next_enabled,
        }.items()
        if value is not None
    }

    if not patch:
        return {
            "success": True,
            "preferences": await _get_visual_preferences(user.user_id),
        }

    preferences = await _save_visual_preferences(user.user_id, patch)
    return {
        "success": True,
        "preferences": preferences,
    }


@router.get("/watchlist")
async def watch_videos_watchlist(
    request: Request,
    limit: int = Query(default=36, ge=1, le=80),
    sort_mode: str = Query(default="", max_length=20),
    sort_dir: str = Query(default="", max_length=10),
):
    user = await require_auth(request)
    await _ensure_seed_catalog()

    plan = _resolve_plan(user)
    prefs = await _get_visual_preferences(user.user_id)
    resolved_mode = sort_mode if sort_mode in {"recent", "duration", "category"} else str(prefs.get("watchlist_sort_mode") or "recent")
    resolved_dir = sort_dir if sort_dir in {"asc", "desc"} else str(prefs.get("watchlist_sort_direction") or "desc")
    feedback_map = await _feedback_map_for_user(user.user_id)
    watchlist_rows = await _watchlist_videos(
        user.user_id,
        plan=plan,
        feedback_map=feedback_map,
        limit=max(1, int(limit)),
        sort_mode=resolved_mode,
        sort_dir=resolved_dir,
    )
    continue_rows = await _continue_watching(
        user.user_id,
        plan=plan,
        feedback_map=feedback_map,
        limit=12,
    )
    return {
        "success": True,
        "watchlist": watchlist_rows,
        "watchlist_count": len(watchlist_rows),
        "continue_queue": continue_rows,
        "sort_mode": resolved_mode,
        "sort_dir": resolved_dir,
        "queue_insight": await _build_queue_insight(
            user,
            watchlist_rows=watchlist_rows,
            continue_rows=continue_rows,
            recommended_rows=[],
        ),
    }


@router.post("/watchlist/toggle")
async def watch_videos_watchlist_toggle(
    payload: VideoWatchlistToggleRequest,
    request: Request,
    sort_mode: str = Query(default="", max_length=20),
    sort_dir: str = Query(default="", max_length=10),
):
    started_at = _now()
    user = await require_auth(request)
    await _ensure_seed_catalog()

    plan = _resolve_plan(user)
    try:
        prefs = await _get_visual_preferences(user.user_id)
        resolved_mode = sort_mode if sort_mode in {"recent", "duration", "category"} else str(prefs.get("watchlist_sort_mode") or "recent")
        resolved_dir = sort_dir if sort_dir in {"asc", "desc"} else str(prefs.get("watchlist_sort_direction") or "desc")
        visible_doc = await db[COLL_CATALOG].find_one(
            {"video_id": payload.video_id, **_visibility_filter(plan)},
            {"_id": 0, "video_id": 1},
        )
        if not visible_doc:
            exists = await db[COLL_CATALOG].find_one({"video_id": payload.video_id}, {"_id": 0, "video_id": 1})
            if exists:
                raise HTTPException(status_code=403, detail="This video requires a higher subscription plan.")
            raise HTTPException(status_code=404, detail="Video not found")

        watchlist_state = await watch_videos_playback_service.toggle_watchlist(user=user, payload=payload)
        watchlisted = bool(watchlist_state.get("watchlisted"))

        feedback_map = await _feedback_map_for_user(user.user_id)
        watchlist_rows = await _watchlist_videos(
            user.user_id,
            plan=plan,
            feedback_map=feedback_map,
            limit=36,
            sort_mode=resolved_mode,
            sort_dir=resolved_dir,
        )
        continue_rows = await _continue_watching(user.user_id, plan=plan, feedback_map=feedback_map, limit=12)
        response_payload = {
            "success": bool(watchlist_state.get("success")),
            "video_id": payload.video_id,
            "watchlisted": watchlisted,
            "watchlist_count": int(watchlist_state.get("watchlist_count") or len(watchlist_rows)),
            "watchlist": watchlist_rows,
            "continue_queue": continue_rows,
            "sort_mode": resolved_mode,
            "sort_dir": resolved_dir,
            "queue_insight": await _build_queue_insight(
                user,
                watchlist_rows=watchlist_rows,
                continue_rows=continue_rows,
                recommended_rows=[],
            ),
            "updated_at": _now_iso(),
        }
        await _record_api_observability(
            endpoint="watchlist_toggle",
            user_id=user.user_id,
            plan=plan,
            status_code=200,
            duration_ms=_elapsed_ms(started_at),
            source=str(payload.action or "toggle")[:24],
        )
        return response_payload
    except HTTPException as http_exc:
        await _record_api_observability(
            endpoint="watchlist_toggle",
            user_id=user.user_id,
            plan=plan,
            status_code=http_exc.status_code,
            duration_ms=_elapsed_ms(started_at),
            source=str(payload.action or "toggle")[:24],
            error_code=str(http_exc.detail or "")[:160],
        )
        raise
    except Exception as exc:
        await _record_api_observability(
            endpoint="watchlist_toggle",
            user_id=user.user_id,
            plan=plan,
            status_code=500,
            duration_ms=_elapsed_ms(started_at),
            source=str(payload.action or "toggle")[:24],
            error_code=type(exc).__name__,
        )
        raise


@router.get("/admin/observability")
async def watch_videos_admin_observability(
    request: Request,
    lookback_days: int = Query(default=7, ge=1, le=30),
):
    user = await require_auth(request)
    role = resolve_user_role(user)
    if role not in {"admin", "super_admin", "ops_admin"}:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    now = _now()
    since_24h_iso = (now - timedelta(hours=24)).isoformat()
    since_window_iso = (now - timedelta(days=int(lookback_days))).isoformat()
    api_coll = db[COLL_API_OBSERVABILITY]

    total_calls_24h = await api_coll.count_documents({"created_at": {"$gte": since_24h_iso}})
    total_errors_24h = await api_coll.count_documents({"created_at": {"$gte": since_24h_iso}, "status_code": {"$gte": 400}})
    watch_calls_24h = await api_coll.count_documents({"endpoint": "watch", "created_at": {"$gte": since_24h_iso}})
    watch_errors_24h = await api_coll.count_documents({"endpoint": "watch", "created_at": {"$gte": since_24h_iso}, "status_code": {"$gte": 400}})
    quota_rejections_24h = await api_coll.count_documents({"endpoint": "watch", "created_at": {"$gte": since_24h_iso}, "status_code": 429})

    latency_rows = await api_coll.find(
        {
            "endpoint": "watch",
            "created_at": {"$gte": since_window_iso},
            "status_code": {"$lt": 400},
        },
        {"_id": 0, "duration_ms": 1, "source": 1},
    ).limit(8000).to_list(8000)
    watch_latencies = [max(0, int(row.get("duration_ms") or 0)) for row in latency_rows]
    fallback_count = sum(1 for row in latency_rows if "fallback" in str(row.get("source") or "").lower())

    history_rows = await db[COLL_WATCH_HISTORY].find(
        {"last_watched_at": {"$gte": since_window_iso}},
        {
            "_id": 0,
            "user_id": 1,
            "progress_seconds": 1,
            "completion_ratio": 1,
            "completed": 1,
            "last_watched_at": 1,
        },
    ).limit(8000).to_list(8000)
    progress_values = [max(0, int(row.get("progress_seconds") or 0)) for row in history_rows]
    completion_samples = [
        float(row.get("completion_ratio") or 0.0)
        for row in history_rows
    ]
    completed_count = sum(1 for row in history_rows if bool(row.get("completed")) or float(row.get("completion_ratio") or 0) >= 0.98)
    completion_rate_pct = _safe_pct(completed_count, len(completion_samples))

    active_users_window = await db[COLL_WATCH_HISTORY].distinct("user_id", {"last_watched_at": {"$gte": since_window_iso}})
    active_users_24h = await db[COLL_WATCH_HISTORY].distinct("user_id", {"last_watched_at": {"$gte": since_24h_iso}})
    watchlist_users_window = await db[COLL_WATCHLIST].distinct("user_id", {"updated_at": {"$gte": since_window_iso}})

    usage_today = await db[COLL_WATCH_USAGE].find(
        {"day_key": _today_key()},
        {"_id": 0, "user_id": 1, "plan": 1},
    ).limit(12000).to_list(12000)
    usage_per_user: dict[str, dict[str, Any]] = {}
    for row in usage_today:
        user_id = str(row.get("user_id") or "")
        if not user_id:
            continue
        slot = usage_per_user.setdefault(user_id, {"count": 0, "plan": str(row.get("plan") or "free")})
        slot["count"] = int(slot.get("count") or 0) + 1
        if row.get("plan"):
            slot["plan"] = str(row.get("plan"))

    pressure_users = 0
    finite_users = 0
    for slot in usage_per_user.values():
        plan = str(slot.get("plan") or "free")
        cap = int(PLAN_DAILY_WATCH_CAPS.get(plan, 0))
        if cap <= 0:
            continue
        finite_users += 1
        if (int(slot.get("count") or 0) / max(1, cap)) >= 0.8:
            pressure_users += 1

    timeline_rows = await api_coll.find(
        {"created_at": {"$gte": since_24h_iso}},
        {
            "_id": 0,
            "endpoint": 1,
            "status_code": 1,
            "duration_ms": 1,
            "created_at": 1,
        },
    ).sort("created_at", 1).limit(24000).to_list(24000)

    hourly_buckets: dict[str, dict[str, Any]] = {}
    for row in timeline_rows:
        created_at_raw = str(row.get("created_at") or "").strip()
        if not created_at_raw:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue

        hour_key = created_dt.replace(minute=0, second=0, microsecond=0).isoformat()
        bucket = hourly_buckets.setdefault(
            hour_key,
            {
                "total_calls": 0,
                "errors": 0,
                "watch_calls": 0,
                "watch_errors": 0,
                "quota_rejections": 0,
                "watch_latencies": [],
            },
        )

        endpoint = str(row.get("endpoint") or "")
        status_code = int(row.get("status_code") or 0)
        duration_ms = max(0, int(row.get("duration_ms") or 0))

        bucket["total_calls"] = int(bucket.get("total_calls") or 0) + 1
        if status_code >= 400:
            bucket["errors"] = int(bucket.get("errors") or 0) + 1
        if endpoint == "watch":
            bucket["watch_calls"] = int(bucket.get("watch_calls") or 0) + 1
            if status_code >= 400:
                bucket["watch_errors"] = int(bucket.get("watch_errors") or 0) + 1
            if status_code < 400:
                latencies = bucket.get("watch_latencies")
                if isinstance(latencies, list):
                    latencies.append(duration_ms)
        if endpoint == "watch" and status_code == 429:
            bucket["quota_rejections"] = int(bucket.get("quota_rejections") or 0) + 1

    bucket_values = list(hourly_buckets.values())
    baseline_error_rates = [
        _safe_pct(bucket.get("errors") or 0, bucket.get("total_calls") or 0)
        for bucket in bucket_values
        if int(bucket.get("total_calls") or 0) >= 5
    ]
    baseline_watch_p95_values = [
        _percentile(bucket.get("watch_latencies") or [], 95)
        for bucket in bucket_values
        if len(bucket.get("watch_latencies") or []) >= 5
    ]
    baseline_error_rate = round(sum(baseline_error_rates) / len(baseline_error_rates), 2) if baseline_error_rates else 0.0
    baseline_watch_p95 = int(round(sum(baseline_watch_p95_values) / len(baseline_watch_p95_values))) if baseline_watch_p95_values else 0

    incident_timeline: list[dict[str, Any]] = []
    for hour_key in sorted(hourly_buckets.keys(), reverse=True):
        bucket = hourly_buckets.get(hour_key) or {}
        total_calls = int(bucket.get("total_calls") or 0)
        watch_calls = int(bucket.get("watch_calls") or 0)
        errors = int(bucket.get("errors") or 0)
        watch_errors = int(bucket.get("watch_errors") or 0)
        quota_rejections = int(bucket.get("quota_rejections") or 0)
        watch_latencies = bucket.get("watch_latencies") or []
        error_rate_pct = _safe_pct(errors, total_calls)
        watch_error_rate_pct = _safe_pct(watch_errors, watch_calls)
        watch_p95_ms = _percentile(watch_latencies, 95) if watch_latencies else 0

        error_threshold = max(8.0, baseline_error_rate * 1.8 if baseline_error_rate > 0 else 8.0)
        latency_threshold = max(1800, int(round((baseline_watch_p95 or 1) * 1.5)))

        error_spike = total_calls >= 6 and error_rate_pct >= error_threshold
        latency_spike = len(watch_latencies) >= 6 and watch_p95_ms >= latency_threshold
        quota_spike = quota_rejections >= 4

        if not (error_spike or latency_spike or quota_spike):
            continue

        signal_type = "error_spike"
        severity = "medium"
        title = "Error spike detected"
        if error_spike:
            signal_type = "error_spike"
            severity = "high" if error_rate_pct >= 20 or errors >= 6 else "medium"
            title = "Error spike detected"
        elif latency_spike:
            signal_type = "latency_spike"
            severity = "high" if watch_p95_ms >= 2600 else "medium"
            title = "Latency spike detected"
        elif quota_spike:
            signal_type = "quota_spike"
            severity = "medium"
            title = "Quota pressure spike detected"

        incident_timeline.append(
            {
                "hour_bucket": hour_key,
                "signal_type": signal_type,
                "severity": severity,
                "title": title,
                "metrics": {
                    "total_calls": total_calls,
                    "error_rate_pct": error_rate_pct,
                    "watch_error_rate_pct": watch_error_rate_pct,
                    "watch_p95_ms": watch_p95_ms,
                    "quota_rejections": quota_rejections,
                },
                "suggested_actions": _observability_incident_actions(signal_type),
            }
        )

        if len(incident_timeline) >= 6:
            break

    incident_hours = {str(item.get("hour_bucket") or "") for item in incident_timeline}
    trend_start_hour = (now - timedelta(hours=23)).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    incident_volume_points: list[dict[str, Any]] = []
    for offset in range(24):
        hour_dt = trend_start_hour + timedelta(hours=offset)
        hour_key = hour_dt.isoformat()
        bucket = hourly_buckets.get(hour_key) or {}
        total_calls = int(bucket.get("total_calls") or 0)
        errors = int(bucket.get("errors") or 0)
        quota_rejections = int(bucket.get("quota_rejections") or 0)
        incident_events = int(errors + quota_rejections)
        incident_volume_points.append(
            {
                "hour_bucket": hour_key,
                "hour_label": hour_dt.strftime("%H:%M"),
                "total_calls": total_calls,
                "errors": errors,
                "quota_rejections": quota_rejections,
                "incident_events": incident_events,
                "incident_spike": hour_key in incident_hours,
            }
        )

    max_incident_events = max((int(point.get("incident_events") or 0) for point in incident_volume_points), default=0)
    max_total_calls = max((int(point.get("total_calls") or 0) for point in incident_volume_points), default=0)

    return {
        "success": True,
        "feature_id": FEATURE_ID,
        "feature_route": FEATURE_ROUTE,
        "lookback_days": int(lookback_days),
        "generated_at": _now_iso(),
        "api": {
            "total_calls_24h": int(total_calls_24h),
            "total_errors_24h": int(total_errors_24h),
            "error_rate_pct_24h": _safe_pct(total_errors_24h, total_calls_24h),
            "watch_calls_24h": int(watch_calls_24h),
            "watch_errors_24h": int(watch_errors_24h),
            "watch_error_rate_pct_24h": _safe_pct(watch_errors_24h, watch_calls_24h),
            "watch_latency_ms": {
                "p50": _percentile(watch_latencies, 50),
                "p95": _percentile(watch_latencies, 95),
                "samples": len(watch_latencies),
            },
        },
        "engagement": {
            "active_users_24h": len(active_users_24h),
            "active_users_window": len(active_users_window),
            "watch_events_today": len(usage_today),
            "progress_seconds": {
                "p50": _percentile(progress_values, 50),
                "p95": _percentile(progress_values, 95),
                "samples": len(progress_values),
            },
            "completion_rate_pct_window": completion_rate_pct,
        },
        "risk_signals": {
            "quota_rejections_24h": int(quota_rejections_24h),
            "fallback_stream_rate_pct_window": _safe_pct(fallback_count, len(latency_rows)),
            "watchlist_adoption_rate_pct_window": _safe_pct(len(watchlist_users_window), len(active_users_window)),
            "quota_pressure_rate_pct_today": _safe_pct(pressure_users, finite_users),
        },
        "incident_timeline": incident_timeline,
        "incident_timeline_summary": {
            "hours_scanned": len(hourly_buckets),
            "spikes_detected": len(incident_timeline),
            "baseline_error_rate_pct_24h": baseline_error_rate,
            "baseline_watch_p95_ms_24h": baseline_watch_p95,
        },
        "incident_volume_trend_24h": {
            "points": incident_volume_points,
            "max_incident_events": int(max_incident_events),
            "max_total_calls": int(max_total_calls),
        },
    }


@router.get("/admin/observability/incident-timeline.csv")
async def watch_videos_admin_observability_incident_timeline_csv(
    request: Request,
    lookback_days: int = Query(default=7, ge=1, le=30),
):
    observability_payload = await watch_videos_admin_observability(request=request, lookback_days=lookback_days)
    timeline_rows = observability_payload.get("incident_timeline") or []
    csv_content = _build_incident_timeline_csv(timeline_rows)
    filename = f"watch-videos-incident-timeline-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/admin/visual-theme")
async def watch_videos_admin_visual_theme(request: Request):
    user = await require_auth(request)
    role = resolve_user_role(user)
    if role not in {"admin", "super_admin", "ops_admin"}:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    config = await _save_visual_theme_config(await _get_visual_theme_config())
    return {
        "success": True,
        "visual_theme": config,
        "style_pack_options": sorted(STYLE_PACKS),
    }


@router.post("/admin/style-pack")
async def watch_videos_admin_style_pack(payload: VideoStylePackUpdateRequest, request: Request):
    user = await require_auth(request)
    role = resolve_user_role(user)
    if role not in {"admin", "super_admin", "ops_admin"}:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    category = str(payload.category or "all").strip()
    style_pack = str(payload.style_pack or "cinematic")
    config = await _get_visual_theme_config()
    style_map = dict(config.get("category_style_packs") or _default_category_style_packs())

    if category.lower() == "all":
        for key in list(style_map.keys()):
            style_map[key] = style_pack
        config["default_style_pack"] = style_pack
        category_filter = None
    else:
        valid_categories = {str(profile.get("name") or "") for profile in CATEGORY_PROFILES}
        if category not in valid_categories:
            raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")
        style_map[category] = style_pack
        category_filter = category

    config["category_style_packs"] = style_map
    saved_config = await _save_visual_theme_config(config)
    applied = await _apply_visual_theme_to_catalog(db[COLL_CATALOG], category_filter=category_filter)
    return {
        "success": True,
        "updated_category": category,
        "style_pack": style_pack,
        "applied": applied,
        "visual_theme": saved_config,
    }


@router.post("/admin/regenerate-visual-theme")
async def watch_videos_admin_regenerate_visual_theme(
    request: Request,
    payload: VideoRegenerateThemeRequest | None = None,
):
    user = await require_auth(request)
    role = resolve_user_role(user)
    if role not in {"admin", "super_admin", "ops_admin"}:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    config = await _get_visual_theme_config()
    if bool(payload.force_new_cycle if payload else True):
        config["theme_cycle"] = f"cycle-{uuid.uuid4().hex[:10]}"

    saved_config = await _save_visual_theme_config(config)
    applied = await _apply_visual_theme_to_catalog(db[COLL_CATALOG])
    return {
        "success": True,
        "visual_theme": saved_config,
        "applied": applied,
        "note": "Visual theme regenerated across catalog",
    }


@router.post("/admin/run-daily-drop")
async def run_watch_videos_daily_drop_admin(request: Request, force: bool = False):
    user = await require_auth(request)
    if not bool(user.is_admin):
        raise HTTPException(status_code=403, detail="Admin access required")

    return await run_watch_videos_daily_drop(
        triggered_by=f"admin:{user.user_id}",
        force=bool(force),
    )
