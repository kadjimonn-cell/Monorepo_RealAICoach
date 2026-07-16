"""Feature Registry — Dynamic, DB-backed feature catalog with real-time sync.

All platform features are stored in MongoDB and served via API.
Changes broadcast via WebSocket so all connected clients update instantly.
"""

from fastapi import APIRouter, Request, HTTPException, Response
from datetime import datetime, timezone, timedelta
import logging
import copy
import json
import hashlib
from collections import defaultdict
from typing import Optional, Any
from pydantic import BaseModel, Field
from utils.access_control_engine import compute_effective_plan

logger = logging.getLogger("routes.feature_registry")
router = APIRouter()

V2_COLOR_MAP = {
    "#3B82F6": "#0F766E",
    "#0EA5E9": "#14B8A6",
    "#7C3AED": "#14B8A6",
    "#6366F1": "#0F766E",
    "#2563EB": "#0F766E",
    "#D946EF": "#5EEAD4",
    "#06B6D4": "#14B8A6",
    "#8B5CF6": "#14B8A6",
    "#A78BFA": "#5EEAD4",
    "#00D4AA": "#14B8A6",
}

FEATURE_REBRAND_OVERRIDES = {
    "ai-writer": {
        "title": "Smart Writing Studio",
        "description": "Create, rewrite, and polish professional content with guided AI writing workflows.",
    },
    "ai-chatbot": {
        "title": "Personal AI Assistant",
        "description": "Run persistent AI conversations for planning, problem-solving, and daily execution.",
    },
    "ai-search": {
        "title": "Deep Research Navigator",
        "description": "Research topics with multi-step AI synthesis, source-aware summaries, and follow-up guidance.",
    },
    "ai-automations": {
        "title": "Workflow Builder",
        "description": "Design practical trigger-action automations and convert tasks into repeatable workflows.",
    },
    "ai-cognitive": {
        "title": "Decision Coach",
        "description": "Break down complex choices into options, trade-offs, and decision-ready next steps.",
    },
    "school-tutor": {
        "title": "Learning Coach",
        "description": "Get guided tutoring, homework support, and study acceleration in one interactive workspace.",
    },
    "medimate": {
        "title": "Health Guide",
        "description": "Track wellness context and receive practical AI health guidance for daily habits.",
    },
    "fitness": {
        "title": "Fitness Planner Pro",
        "description": "Generate personalized workout and nutrition plans with measurable weekly progress.",
    },
    "pennypilot": {
        "title": "Money Strategy Hub",
        "description": "Plan budgets, savings, and spending decisions with AI-assisted financial guidance.",
    },
    "smartbuy": {
        "title": "Smart Shopping Advisor",
        "description": "Compare options intelligently and optimize purchase decisions for value and timing.",
    },
    "travelpal": {
        "title": "Travel Planner Pro",
        "description": "Build optimized itineraries, budgets, and travel checklists across destinations.",
    },
    "ai-found-love": {
        "title": "Relationship Coach",
        "description": "Improve dating and relationship communication with scenario-based AI coaching.",
    },
    "smart-cars": {
        "title": "Mobility Assistant",
        "description": "Get smarter trip, maintenance, and driving-efficiency recommendations for daily mobility.",
    },
    "buy-smart-home": {
        "title": "Property Decision Advisor",
        "description": "Evaluate properties with structured criteria, affordability signals, and fit insights.",
    },
    "ai-video": {
        "title": "Video Creator Studio",
        "description": "Plan scripts, production steps, and creator workflows for consistent video output.",
    },
    "ai-photo": {
        "title": "Image & Design Studio",
        "description": "Generate and refine visual concepts, creatives, and design directions with AI.",
    },
    "ai-speech": {
        "title": "Voice Studio",
        "description": "Use AI voice workflows for speech generation, analysis, and communication coaching.",
    },
    "ai-enterprise": {
        "title": "Business Operations Copilot",
        "description": "Translate business goals into structured operational action plans and execution guidance.",
    },
    "bill-generator": {
        "title": "Bill Generator",
        "description": "Create branded bills with AI-assisted line items, lifecycle tracking, and payment-ready exports.",
    },
    "lexicon-intelligence": {
        "title": "Lexicon Intelligence Hub",
        "description": "Master high-impact vocabulary daily with communication coaching, spaced review, and business-ready usage drills.",
    },
    "games-station": {
        "title": "FPS Game",
        "description": "Multiplayer first-person shooter: join or create rooms, battle in real time, and climb the kill leaderboard.",
    },
    "travel-visa": {
        "title": "Travel Visa",
        "description": "AI-powered visa coaching, interview preparation, and immigration learning.",
    },
    "daily-meditation": {
        "title": "Daily Meditation",
        "description": "Faith-centered daily reflection with companion guidance, reminders, and progress insights.",
    },
    "ai-learning-hub": {
        "title": "Learning Hub",
        "description": "AI-guided lessons, practice journeys, and progress coaching in one learning workspace.",
    },
    "flappy-bird": {
        "title": "Flappy Bird Game",
        "description": "Classic arcade flying challenge: flap through the pipes, chase your personal best, and climb the high-score leaderboard.",
    },
}


def _looks_like_placeholder_feature_copy(value: Any) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    return lowered in {"title", "subtitle", "description", "count label", "sous-titre", "titre", "name", "nom"}

FEATURE_LOCALIZED_FALLBACKS = {
    "free": "Free",
}


def _looks_like_placeholder_feature_copy(value: Any) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    placeholder_values = {
        "title",
        "subtitle",
        "description",
        "count label",
        "sous-titre",
        "titre",
        "nom",
        "name",
    }
    return lowered in placeholder_values

LEXICON_REGISTRY_DEFAULT = {
    "feature_id": "lexicon-intelligence",
    "title": "Lexicon Intelligence Hub",
    "description": "Master high-impact vocabulary daily with communication coaching, spaced review, and business-ready usage drills.",
    "icon": "book",
    "route": "/features/lexicon-intelligence",
    "category": "productivity",
    "color": "#14B8A6",
    "is_new": True,
    "premium": False,
    "enabled": True,
}


_lexicon_registry_checked = False
_core_registry_check_ts = 0.0
_CORE_REGISTRY_CHECK_TTL_SECONDS = 120.0

CORE_SIDENAV_FEATURE_DEFAULTS = [
    {
        "feature_id": "games-station",
        "title": "FPS Game",
        "description": "Multiplayer first-person shooter: join or create rooms, battle in real time, and climb the kill leaderboard.",
        "icon": "locate",
        "route": "/features/fps-game",
        "category": "entertainment",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "watch-videos",
        "title": "Watch Videos",
        "description": "Browse and watch curated videos with AI-assisted discovery and recommendations.",
        "icon": "film",
        "route": "/features/watch-videos",
        "category": "entertainment",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "audio-studio",
        "title": "Audio Studio",
        "description": "Create, edit, and manage AI-assisted audio workflows from one studio route.",
        "icon": "musical-notes",
        "route": "/features/audio-studio",
        "category": "media",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "my-podcasts",
        "title": "My Podcasts",
        "description": "Manage your podcast episodes, publishing queue, and listening flow.",
        "icon": "mic",
        "route": "/features/my-podcasts",
        "category": "media",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "sports",
        "title": "Sports",
        "description": "Track matchday updates, insights, and sports intelligence workflows.",
        "icon": "american-football",
        "route": "/features/sports",
        "category": "entertainment",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "travel-visa",
        "title": "Travel Visa",
        "description": "AI-powered visa coaching, interview preparation, and immigration learning.",
        "icon": "airplane",
        "route": "/features/travel-visa",
        "category": "travel",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "daily-meditation",
        "title": "Daily Meditation",
        "description": "Faith-centered daily reflection, journaling, and calm companion guidance with reminder support.",
        "icon": "leaf",
        "route": "/features/daily-meditation",
        "category": "wellness",
        "color": "#14B8A6",
        "is_new": True,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "ai-learning-hub",
        "title": "Learning Hub",
        "description": "AI-guided lessons, practice journeys, and progress coaching in one learning workspace.",
        "icon": "school",
        "route": "/ai-learning-hub",
        "category": "education",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "ai-coaching-team",
        "title": "AI Coaching Team",
        "description": "Chat with a curated team of AI coaches for career, interviews, resumes, and negotiation.",
        "icon": "people",
        "route": "/ai-coaching-team",
        "category": "productivity",
        "color": "#14B8A6",
        "is_new": True,
        "premium": True,
        "enabled": True,
    },
    {
        "feature_id": "ai-briefing",
        "title": "Daily Briefing",
        "description": "Get AI-generated daily summaries, priorities, and action-ready insights.",
        "icon": "newspaper",
        "route": "/ai-briefing",
        "category": "productivity",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "library",
        "title": "Library",
        "description": "Access saved knowledge, content collections, and study resources.",
        "icon": "book",
        "route": "/content-library",
        "category": "education",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "book-meeting",
        "title": "My Agenda",
        "description": "Plan and manage meetings, schedule blocks, and agenda workflows.",
        "icon": "calendar",
        "route": "/book-meeting",
        "category": "productivity",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "integrations",
        "title": "Integrations",
        "description": "Connect external services and sync workflows across the platform.",
        "icon": "git-network",
        "route": "/integrations",
        "category": "productivity",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "jobs-portal",
        "title": "Job Search",
        "description": "AI-powered job search: profile evaluation, fit scoring, tailored CV and cover letters, ATS validation.",
        "icon": "search",
        "route": "/job-search",
        "category": "career",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "referrals",
        "title": "Referral Program",
        "description": "Track invitations, referral rewards, and growth performance.",
        "icon": "gift",
        "route": "/referrals",
        "category": "growth",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "id-checker",
        "title": "ID Checker",
        "description": "Run identity verification checks and secure document validation workflows.",
        "icon": "finger-print",
        "route": "/id-checker",
        "category": "security",
        "color": "#14B8A6",
        "is_new": False,
        "premium": False,
        "enabled": True,
    },
    {
        "feature_id": "flappy-bird",
        "title": "Flappy Bird Game",
        "description": "Classic arcade flying challenge: flap through the pipes, chase your personal best, and climb the high-score leaderboard.",
        "icon": "paper-plane",
        "route": "/features/flappy-bird",
        "category": "entertainment",
        "color": "#14B8A6",
        "is_new": True,
        "premium": False,
        "enabled": True,
    },
]


# Locked canonical sequence (Checkpoint-governed). This order must remain stable
# for the core 36 features regardless of mutable runtime sort operations.
LOCKED_CANONICAL_FEATURE_ORDER: list[dict] = [
    {"feature_number": 1, "batch": 1, "feature_id": "ai-writer"},
    {"feature_number": 2, "batch": 1, "feature_id": "ai-chatbot"},
    {"feature_number": 3, "batch": 1, "feature_id": "ai-search"},
    {"feature_number": 4, "batch": 1, "feature_id": "ai-automations"},
    {"feature_number": 5, "batch": 1, "feature_id": "ai-cognitive"},
    {"feature_number": 6, "batch": 1, "feature_id": "school-tutor"},
    {"feature_number": 7, "batch": 2, "feature_id": "medimate"},
    {"feature_number": 8, "batch": 2, "feature_id": "fitness"},
    {"feature_number": 9, "batch": 2, "feature_id": "pennypilot"},
    {"feature_number": 10, "batch": 2, "feature_id": "smartbuy"},
    {"feature_number": 11, "batch": 2, "feature_id": "travelpal"},
    {"feature_number": 12, "batch": 2, "feature_id": "ai-found-love"},
    {"feature_number": 13, "batch": 3, "feature_id": "smart-cars"},
    {"feature_number": 14, "batch": 3, "feature_id": "buy-smart-home"},
    {"feature_number": 15, "batch": 3, "feature_id": "ai-video"},
    {"feature_number": 16, "batch": 3, "feature_id": "ai-photo"},
    {"feature_number": 17, "batch": 3, "feature_id": "ai-speech"},
    {"feature_number": 18, "batch": 3, "feature_id": "ai-enterprise"},
    {"feature_number": 19, "batch": 4, "feature_id": "bill-generator"},
    {"feature_number": 20, "batch": 4, "feature_id": "lexicon-intelligence"},
    {"feature_number": 21, "batch": 4, "feature_id": "watch-videos"},
    {"feature_number": 22, "batch": 4, "feature_id": "games-station"},
    {"feature_number": 23, "batch": 4, "feature_id": "travel-visa"},
    {"feature_number": 24, "batch": 4, "feature_id": "ai-learning-hub"},
    {"feature_number": 25, "batch": 4, "feature_id": "daily-meditation"},
    {"feature_number": 26, "batch": 4, "feature_id": "jobs-portal"},
    {"feature_number": 27, "batch": 4, "feature_id": "id-checker"},
    {"feature_number": 28, "batch": 5, "feature_id": "audio-studio"},
    {"feature_number": 29, "batch": 5, "feature_id": "my-podcasts"},
    {"feature_number": 30, "batch": 5, "feature_id": "sports"},
    {"feature_number": 31, "batch": 5, "feature_id": "ai-coaching-team"},
    {"feature_number": 32, "batch": 5, "feature_id": "ai-briefing"},
    {"feature_number": 33, "batch": 5, "feature_id": "library"},
    {"feature_number": 34, "batch": 5, "feature_id": "book-meeting"},
    {"feature_number": 35, "batch": 5, "feature_id": "integrations"},
    {"feature_number": 36, "batch": 5, "feature_id": "referrals"},
    {"feature_number": 37, "batch": 6, "feature_id": "flappy-bird"},
]

LOCKED_CANONICAL_FEATURE_IDS = [item["feature_id"] for item in LOCKED_CANONICAL_FEATURE_ORDER]
LOCKED_CANONICAL_FEATURE_NUMBER = {item["feature_id"]: int(item["feature_number"]) for item in LOCKED_CANONICAL_FEATURE_ORDER}
LOCKED_CANONICAL_FEATURE_BATCH = {item["feature_id"]: int(item["batch"]) for item in LOCKED_CANONICAL_FEATURE_ORDER}
LOCKED_CANONICAL_FEATURE_SORT_ORDER = {
    item["feature_id"]: int(item["feature_number"]) - 1 for item in LOCKED_CANONICAL_FEATURE_ORDER
}
CANONICAL_ORDER_VERSION = "2026-06-14.v2"


def _safe_int(value: object, fallback: int = 9999) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _canonical_sort_order_for_feature(feature_id: str, fallback: int) -> int:
    return int(LOCKED_CANONICAL_FEATURE_SORT_ORDER.get(feature_id, fallback))


def _canonical_rank(feature_id: str) -> int:
    number = LOCKED_CANONICAL_FEATURE_NUMBER.get(feature_id)
    if number is None:
        return 10_000
    return int(number)


def _sort_features_by_canonical_order(features: list[dict]) -> list[dict]:
    return sorted(
        features,
        key=lambda row: (
            _canonical_rank(str(row.get("feature_id") or row.get("id") or "").strip()),
            _safe_int(row.get("sort_order"), 9999),
            str(row.get("feature_id") or row.get("id") or "").strip(),
        ),
    )


def _build_canonical_order_manifest_payload() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest_items = [
        {
            "feature_number": int(item["feature_number"]),
            "feature_id": str(item["feature_id"]),
            "feature_batch": int(item["batch"]),
            "expected_sort_order": int(item["feature_number"]) - 1,
        }
        for item in LOCKED_CANONICAL_FEATURE_ORDER
    ]

    payload_for_hash = {
        "canonical_order_version": CANONICAL_ORDER_VERSION,
        "items": manifest_items,
    }
    content_hash = hashlib.sha256(
        json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "manifest_name": "canonical_order_manifest.json",
        "generated_at": generated_at,
        "canonical_order_version": CANONICAL_ORDER_VERSION,
        "locked_feature_count": len(LOCKED_CANONICAL_FEATURE_IDS),
        "content_hash_sha256": content_hash,
        "items": manifest_items,
    }


async def _build_canonical_audit_payload(db) -> dict[str, Any]:
    rows = await db.feature_registry.find(
        {},
        {
            "_id": 0,
            "feature_id": 1,
            "title": 1,
            "route": 1,
            "enabled": 1,
            "sort_order": 1,
            "feature_number": 1,
            "feature_batch": 1,
            "updated_at": 1,
        },
    ).to_list(2000)

    by_feature_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        feature_id = str(row.get("feature_id") or "").strip()
        if feature_id:
            by_feature_id[feature_id] = row

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _safe_int(row.get("sort_order"), 9999),
            str(row.get("feature_id") or "").strip(),
        ),
    )
    observed_position_map: dict[str, int] = {
        str(row.get("feature_id") or "").strip(): idx
        for idx, row in enumerate(sorted_rows)
        if str(row.get("feature_id") or "").strip()
    }

    missing_locked_feature_ids: list[str] = []
    drifted_features: list[dict[str, Any]] = []

    for canonical in LOCKED_CANONICAL_FEATURE_ORDER:
        feature_id = str(canonical["feature_id"])
        expected_feature_number = int(canonical["feature_number"])
        expected_batch = int(canonical["batch"])
        expected_sort_order = expected_feature_number - 1

        row = by_feature_id.get(feature_id)
        if not row:
            missing_locked_feature_ids.append(feature_id)
            continue

        actual_sort_order = _safe_int(row.get("sort_order"), -1)
        actual_feature_number_raw = row.get("feature_number")
        actual_feature_number = _safe_int(actual_feature_number_raw, -1) if actual_feature_number_raw is not None else -1
        actual_feature_batch_raw = row.get("feature_batch")
        actual_feature_batch = _safe_int(actual_feature_batch_raw, -1) if actual_feature_batch_raw is not None else -1
        observed_position = observed_position_map.get(feature_id, -1)

        is_drifted = (
            actual_sort_order != expected_sort_order
            or actual_feature_number != expected_feature_number
            or actual_feature_batch != expected_batch
            or observed_position != expected_sort_order
        )

        if is_drifted:
            drifted_features.append(
                {
                    "feature_id": feature_id,
                    "title": row.get("title"),
                    "route": row.get("route"),
                    "expected": {
                        "feature_number": expected_feature_number,
                        "feature_batch": expected_batch,
                        "sort_order": expected_sort_order,
                        "position": expected_sort_order,
                    },
                    "actual": {
                        "feature_number": actual_feature_number_raw,
                        "feature_batch": actual_feature_batch_raw,
                        "sort_order": row.get("sort_order"),
                        "position": observed_position,
                    },
                    "updated_at": row.get("updated_at"),
                }
            )

    extra_registry_feature_ids = sorted(
        [
            feature_id
            for feature_id in by_feature_id.keys()
            if feature_id not in LOCKED_CANONICAL_FEATURE_NUMBER
        ]
    )

    locked_feature_count = len(LOCKED_CANONICAL_FEATURE_IDS)
    locked_present_count = locked_feature_count - len(missing_locked_feature_ids)
    has_drift = bool(missing_locked_feature_ids or drifted_features)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "order_policy": {
            "source": "locked_canonical_36",
            "canonical_order_version": CANONICAL_ORDER_VERSION,
            "locked_feature_count": locked_feature_count,
        },
        "summary": {
            "status": "drift_detected" if has_drift else "aligned",
            "registry_feature_count": len(rows),
            "locked_present_count": locked_present_count,
            "missing_locked_feature_count": len(missing_locked_feature_ids),
            "drifted_locked_feature_count": len(drifted_features),
            "extra_non_locked_feature_count": len(extra_registry_feature_ids),
        },
        "missing_locked_feature_ids": missing_locked_feature_ids,
        "drifted_locked_features": drifted_features,
        "extra_non_locked_feature_ids": extra_registry_feature_ids,
        "manifest": {
            "download_endpoint": "/api/features/canonical-order-manifest",
            "filename": "canonical_order_manifest.json",
        },
    }


async def _enforce_locked_canonical_sort_order(db, features: list[dict]) -> bool:
    updates: list[tuple[str, int]] = []
    for feature in features:
        feature_id = str(feature.get("feature_id") or "").strip()
        if not feature_id:
            continue
        expected = LOCKED_CANONICAL_FEATURE_SORT_ORDER.get(feature_id)
        if expected is None:
            continue
        current = _safe_int(feature.get("sort_order"), -1)
        if current != int(expected):
            updates.append((feature_id, int(expected)))

    if not updates:
        return False

    now = datetime.now(timezone.utc).isoformat()
    for feature_id, expected in updates:
        await db.feature_registry.update_one(
            {"feature_id": feature_id},
            {"$set": {"sort_order": expected, "updated_at": now}},
        )

    logger.warning(
        "Canonical feature order drift detected and repaired for feature_ids=%s",
        [item[0] for item in updates],
    )
    return True


async def _ensure_lexicon_registry_feature(db) -> None:
    global _lexicon_registry_checked
    if _lexicon_registry_checked:
        return

    existing = await db.feature_registry.find_one({"feature_id": "lexicon-intelligence"}, {"_id": 0, "feature_id": 1})
    if existing:
        _lexicon_registry_checked = True
        return

    now = datetime.now(timezone.utc).isoformat()
    max_order = await db.feature_registry.find_one({}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)])
    next_order = (int(max_order.get("sort_order") or 0) + 1) if max_order else 0
    feature_doc = {
        **LEXICON_REGISTRY_DEFAULT,
        "sort_order": _canonical_sort_order_for_feature("lexicon-intelligence", next_order),
        "created_at": now,
        "updated_at": now,
    }

    await db.feature_registry.insert_one(feature_doc)
    _registry_cache["ts"] = 0
    _lexicon_registry_checked = True

    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason="Lexicon Intelligence Hub auto-registration",
            actor_user_id="",
            event_type="FeatureAdded",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (lexicon auto-registration): {exc}")


async def _ensure_core_sidenav_features(db) -> None:
    """Guarantee that side-navigation live features are represented in feature registry."""
    global _core_registry_check_ts
    import time

    now_monotonic = time.time()
    if (now_monotonic - _core_registry_check_ts) < _CORE_REGISTRY_CHECK_TTL_SECONDS:
        return

    required_ids = [f["feature_id"] for f in CORE_SIDENAV_FEATURE_DEFAULTS]
    existing_rows = await db.feature_registry.find(
        {"feature_id": {"$in": required_ids}},
        {"_id": 0, "feature_id": 1},
    ).to_list(len(required_ids))
    existing_ids = {str(row.get("feature_id") or "").strip() for row in existing_rows}

    missing = [f for f in CORE_SIDENAV_FEATURE_DEFAULTS if f["feature_id"] not in existing_ids]
    if not missing:
        _core_registry_check_ts = now_monotonic
        return

    max_order = await db.feature_registry.find_one({}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)])
    next_order = (int(max_order.get("sort_order") or 0) + 1) if max_order else 0
    created_at = datetime.now(timezone.utc).isoformat()

    for feature in missing:
        feature_id = str(feature.get("feature_id") or "").strip()
        feature_doc = {
            **feature,
            "sort_order": _canonical_sort_order_for_feature(feature_id, next_order),
            "created_at": created_at,
            "updated_at": created_at,
        }
        next_order += 1
        await db.feature_registry.insert_one(feature_doc)

    _registry_cache["ts"] = 0
    _core_registry_check_ts = now_monotonic
    logger.info(f"Auto-registered missing side-nav features in feature_registry: {[f['feature_id'] for f in missing]}")

    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason="Core side-nav feature auto-registration",
            actor_user_id="",
            event_type="FeatureAdded",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (core side-nav auto-registration): {exc}")


def _normalize_feature_color(color: str) -> str:
    if not color:
        return "#14B8A6"
    return V2_COLOR_MAP.get(str(color).upper(), color)


def _normalize_feature_payload(feature: dict) -> dict:
    payload = copy.deepcopy(feature or {})
    payload.pop("_id", None)
    feature_id = str(payload.get("feature_id") or payload.get("id") or "").strip()
    payload["color"] = _normalize_feature_color(payload.get("color"))
    override = FEATURE_REBRAND_OVERRIDES.get(feature_id)
    if override:
        payload["title"] = override.get("title", payload.get("title"))
        payload["description"] = override.get("description", payload.get("description"))

    if _looks_like_placeholder_feature_copy(payload.get("title")):
        payload["title"] = str(payload.get("feature_id") or payload.get("route") or "Feature").replace("-", " ").replace("_", " ").title()
    if _looks_like_placeholder_feature_copy(payload.get("description")):
        payload["description"] = f"Open {payload.get('title', 'this feature')} and continue your workflow with AI-guided support."

    if _looks_like_placeholder_feature_copy(payload.get("title")):
        payload["title"] = str(payload.get("feature_id") or payload.get("route") or "Feature").replace("-", " ").replace("_", " ").title()
    if _looks_like_placeholder_feature_copy(payload.get("description")):
        payload["description"] = f"Open {payload.get('title', 'this feature')} and continue your workflow with AI-guided support."

    canonical_number = LOCKED_CANONICAL_FEATURE_NUMBER.get(feature_id)
    canonical_batch = LOCKED_CANONICAL_FEATURE_BATCH.get(feature_id)
    if canonical_number is not None:
        payload["feature_number"] = int(canonical_number)
        payload["feature_batch"] = int(canonical_batch or 0)
        payload["sort_order"] = int(canonical_number) - 1
        payload["order_source"] = "locked_canonical"
    else:
        payload["feature_number"] = None
        payload["feature_batch"] = None
        payload["order_source"] = "runtime_sort_order"

    return payload

# GPS-only policy: no hardcoded feature definitions or category catalogs are allowed here.


async def _get_db():
    from routes.db import db
    return db


async def _get_live_gps_state() -> dict:
    from routes.global_platform_state import get_global_platform_state

    return await get_global_platform_state()


def _derive_categories_from_features(features: list[dict]) -> list[dict]:
    values = sorted({str(f.get("category") or "general") for f in (features or []) if f.get("enabled", True)})
    return [{"id": "all", "label": "All"}] + [{"id": c, "label": c.replace("-", " ").title()} for c in values]


RETIRED_FEATURE_IDS = {"ai-problem-solver"}


async def seed_features():
    """Seed feature registry from GlobalPlatformState if empty (no hardcoded feature list)."""
    db = await _get_db()
    await db.feature_registry.delete_many({"feature_id": {"$in": list(RETIRED_FEATURE_IDS)}})
    count = await db.feature_registry.count_documents({})
    if count > 0:
        logger.info(f"Feature registry already has {count} features, skipping seed")
        return

    gps_state = await _get_live_gps_state()
    gps_features = (gps_state or {}).get("features") or []
    if not gps_features:
        logger.warning("Feature registry empty and GPS has no features yet; skipping seed.")
        return

    now = datetime.now(timezone.utc).isoformat()
    payload = []
    for i, f in enumerate(gps_features):
        feature_id = str(f.get("feature_id") or f.get("id") or "").strip()
        payload.append(
            {
                "feature_id": feature_id,
                "title": str(f.get("title") or ""),
                "description": str(f.get("description") or ""),
                "icon": str(f.get("icon") or "apps"),
                "route": str(f.get("route") or ""),
                "category": str(f.get("category") or "general"),
                "color": _normalize_feature_color(str(f.get("color") or "#14B8A6")),
                "is_new": bool(f.get("is_new") or f.get("isNew") or False),
                "premium": bool(f.get("premium") or False),
                "enabled": bool(f.get("enabled", True)),
                "sort_order": _canonical_sort_order_for_feature(feature_id, int(f.get("sort_order", i))),
                "created_at": str(f.get("created_at") or now),
                "updated_at": str(f.get("updated_at") or now),
            }
        )
    payload = [item for item in payload if item.get("feature_id")]
    if payload:
        await db.feature_registry.insert_many(payload)
        logger.info(f"Seeded {len(payload)} features into feature_registry from GPS")


# ── Public Endpoints ──────────────────────────────────────────────────────────


_registry_cache = {"ts": 0, "data": None}
_REGISTRY_TTL = 30  # seconds


def _active_visibility_filter() -> dict:
    return {
        "enabled": True,
        "$or": [
            {"soft_deactivated": {"$exists": False}},
            {"soft_deactivated": {"$ne": True}},
        ],
    }


class Phase1SoftHideRequest(BaseModel):
    reason: Optional[str] = Field(default="Phase 1 safe retirement (UI hidden)")
    retirement_tag: Optional[str] = Field(default="phase1_safe_ui_hide")


class Phase1RestoreRequest(BaseModel):
    reason: Optional[str] = Field(default="Phase 1 soft retirement restored")


class Phase2DeactivateRequest(BaseModel):
    reason: Optional[str] = Field(default="Phase 2 retirement (registry deactivated)")
    retirement_tag: Optional[str] = Field(default="phase2_registry_deactivation")
    minimum_soft_hidden_days: int = Field(default=7, ge=0, le=365)


class Phase2RestoreRequest(BaseModel):
    reason: Optional[str] = Field(default="Phase 2 retirement restored by admin")


def _safe_parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _collect_usage_windows(db, cutoff_30: str, cutoff_90: str) -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    usage_30: dict[str, int] = defaultdict(int)
    usage_90: dict[str, int] = defaultdict(int)
    last_used_at: dict[str, str] = {}

    async for doc in db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": cutoff_30}}},
            {"$group": {"_id": "$feature", "count": {"$sum": 1}}},
        ]
    ):
        fid = str(doc.get("_id") or "").strip()
        if fid:
            usage_30[fid] = int(doc.get("count") or 0)

    async for doc in db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": cutoff_90}}},
            {"$group": {"_id": "$feature", "count": {"$sum": 1}, "last_used_at": {"$max": "$created_at"}}},
        ]
    ):
        fid = str(doc.get("_id") or "").strip()
        if fid:
            usage_90[fid] = int(doc.get("count") or 0)
            if doc.get("last_used_at"):
                last_used_at[fid] = str(doc.get("last_used_at"))

    return usage_30, usage_90, last_used_at


def _build_phase2_retirement_row(
    *,
    feature: dict,
    usage_30: dict[str, int],
    usage_90: dict[str, int],
    last_used_at: dict[str, str],
    now: datetime,
) -> dict:
    feature_id = str(feature.get("feature_id") or "").strip()
    c30 = int(usage_30.get(feature_id, 0) or 0)
    c90 = int(usage_90.get(feature_id, 0) or 0)
    is_soft_hidden = bool(feature.get("soft_deactivated", False))
    phase2_deactivated = bool(feature.get("phase2_deactivated", False))

    soft_hidden_days = 0
    soft_hidden_at = _safe_parse_iso_datetime(str(feature.get("soft_deactivated_at") or ""))
    if soft_hidden_at:
        delta = now - soft_hidden_at.astimezone(timezone.utc)
        soft_hidden_days = max(0, int(delta.total_seconds() // 86400))

    blockers: list[str] = []
    if phase2_deactivated:
        blockers.append("Feature is already retired in Phase 2.")
    if not is_soft_hidden:
        blockers.append("Phase 1 soft hide is required before Phase 2 deactivation.")
    if c30 > 0:
        blockers.append("Usage detected in the last 30 days.")
    if c90 > 1:
        blockers.append("Usage exceeds Phase 2 safety threshold in the last 90 days.")
    if soft_hidden_days < 7:
        blockers.append("Soft-hide soak period is below 7 days.")

    phase2_candidate = not blockers
    priority = "ready" if phase2_candidate else ("already_retired" if phase2_deactivated else "review")

    return {
        **feature,
        "usage_30d": c30,
        "usage_90d": c90,
        "last_used_at": last_used_at.get(feature_id),
        "soft_hidden_days": soft_hidden_days,
        "phase2_deactivated": phase2_deactivated,
        "phase2_candidate": phase2_candidate,
        "phase2_candidate_priority": priority,
        "phase2_candidate_reason": (
            "No recent usage and Phase 1 soak period met. Safe for Phase 2 registry deactivation."
            if phase2_candidate
            else None
        ),
        "phase2_blockers": blockers,
    }

@router.get("/features/registry")
async def get_feature_registry(request: Request = None):
    """Public: Get all enabled features. Used by all frontend pages."""
    import time
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "features_registry", 260, 60)
    if blocked:
        return blocked

    now = time.time()
    if _registry_cache["data"] and (now - _registry_cache["ts"]) < _REGISTRY_TTL:
        return copy.deepcopy(_registry_cache["data"])

    try:
        db = await _get_db()
        await _ensure_lexicon_registry_feature(db)
        await _ensure_core_sidenav_features(db)
        features = await db.feature_registry.find(
            _active_visibility_filter(),
            {"_id": 0},
        ).sort("sort_order", 1).to_list(200)

        healed = await _enforce_locked_canonical_sort_order(db, features)
        if healed:
            features = await db.feature_registry.find(
                _active_visibility_filter(),
                {"_id": 0},
            ).sort("sort_order", 1).to_list(200)

        if not features:
            gps_state = await _get_live_gps_state()
            gps_features = (gps_state or {}).get("features") or []
            features = [
                f
                for f in gps_features
                if f.get("enabled", True) and not bool(f.get("soft_deactivated", False))
            ]

        normalized_features = [_normalize_feature_payload(feature) for feature in features]
        normalized_features = _sort_features_by_canonical_order(normalized_features)
        categories = _derive_categories_from_features(normalized_features)
        result = {
            "features": normalized_features,
            "categories": categories,
            "total": len(normalized_features),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "order_policy": {
                "source": "locked_canonical_36",
                "locked_feature_count": len(LOCKED_CANONICAL_FEATURE_IDS),
                "canonical_order_version": CANONICAL_ORDER_VERSION,
            },
        }
        _registry_cache["ts"] = now
        _registry_cache["data"] = copy.deepcopy(result)
        return result
    except Exception as exc:
        logger.warning(f"Feature registry DB read failed, serving stale cache if available: {exc}")
        if _registry_cache["data"]:
            stale = copy.deepcopy(_registry_cache["data"])
            stale["cache_fallback"] = "stale"
            return stale
        return {
            "features": [],
            "categories": [{"id": "all", "label": "All"}],
            "total": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "degraded",
        }


@router.get("/features/hub-insights")
async def get_features_hub_insights(request: Request):
    """Authenticated user insights for enterprise Features hub UX."""
    from routes.auth import get_current_user

    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = await _get_db()
    registry_payload = await get_feature_registry()
    features = registry_payload.get("features") or []
    feature_map = {str(f.get("feature_id") or ""): f for f in features if f.get("feature_id")}

    plan = compute_effective_plan(
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

    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0)
    cutoff_30d_iso = cutoff_30d.isoformat()

    usage_rows = await db.ai_usage_log.find(
        {"user_id": user.user_id, "created_at": {"$gte": cutoff_30d_iso}},
        {"_id": 0, "feature": 1, "created_at": 1},
    ).sort("created_at", -1).limit(1500).to_list(1500)

    usage_counts: dict[str, int] = defaultdict(int)
    active_days: set[str] = set()
    recent_feature_order: list[str] = []

    for row in usage_rows:
        feature_key = str(row.get("feature") or "").strip()
        if not feature_key:
            continue
        usage_counts[feature_key] += 1
        created_at = str(row.get("created_at") or "")
        if created_at:
            active_days.add(created_at[:10])
        if feature_key not in recent_feature_order:
            recent_feature_order.append(feature_key)

    total_sessions_30d = int(sum(usage_counts.values()))
    used_feature_ids = {feature_id for feature_id, count in usage_counts.items() if count > 0}

    global_usage = {}
    async for doc in db.ai_usage_log.aggregate(
        [
            {"$group": {"_id": "$feature", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 80},
        ]
    ):
        key = str(doc.get("_id") or "").strip()
        if key:
            global_usage[key] = int(doc.get("count") or 0)

    recommendation_pool = []
    for feature in features:
        feature_id = str(feature.get("feature_id") or "")
        if not feature_id or feature_id in used_feature_ids:
            continue
        premium = bool(feature.get("premium"))
        if plan == "free" and premium:
            score = global_usage.get(feature_id, 0) * 0.65
        else:
            score = global_usage.get(feature_id, 0)
        recommendation_pool.append((score, feature))

    recommendation_pool.sort(key=lambda row: row[0], reverse=True)

    recently_used = []
    for feature_id in recent_feature_order[:6]:
        feature = feature_map.get(feature_id)
        if not feature:
            continue
        recently_used.append(
            {
                "feature_id": feature_id,
                "title": feature.get("title"),
                "route": feature.get("route"),
                "icon": feature.get("icon"),
                "category": feature.get("category"),
                "usage_count_30d": int(usage_counts.get(feature_id, 0) or 0),
            }
        )

    recommended = []
    for _, feature in recommendation_pool[:8]:
        feature_id = str(feature.get("feature_id") or "")
        recommended.append(
            {
                "feature_id": feature_id,
                "title": feature.get("title"),
                "route": feature.get("route"),
                "icon": feature.get("icon"),
                "category": feature.get("category"),
                "premium": bool(feature.get("premium")),
                "global_popularity": int(global_usage.get(feature_id, 0) or 0),
            }
        )

    daily_spotlight = recommended[:3]

    top_used = sorted(usage_counts.items(), key=lambda item: item[1], reverse=True)
    favorite_category = "general"
    if top_used:
        top_feature = feature_map.get(top_used[0][0])
        if top_feature:
            favorite_category = str(top_feature.get("category") or "general")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subscription_plan": plan,
        "usage_summary": {
            "sessions_30d": total_sessions_30d,
            "active_days_30d": len(active_days),
            "used_features_30d": len(used_feature_ids),
            "favorite_category": favorite_category,
        },
        "recently_used": recently_used,
        "recommended": recommended,
        "daily_spotlight": daily_spotlight,
    }


@router.get("/features")
async def get_feature_registry_alias():
    """Compatibility alias for /api/features."""
    return await get_feature_registry()


@router.get("/features/gallery")
async def get_feature_gallery_alias():
    """Compatibility alias for /api/features/gallery."""
    from routes.feature_gallery import get_gallery_data

    return await get_gallery_data()


async def _build_all_features_admin_payload() -> dict:
    db = await _get_db()
    features = await db.feature_registry.find(
        {},
        {"_id": 0},
    ).sort("sort_order", 1).to_list(500)

    healed = await _enforce_locked_canonical_sort_order(db, features)
    if healed:
        features = await db.feature_registry.find(
            {},
            {"_id": 0},
        ).sort("sort_order", 1).to_list(500)

    normalized = [_normalize_feature_payload(feature) for feature in features]
    normalized = _sort_features_by_canonical_order(normalized)
    return {
        "features": normalized,
        "categories": _derive_categories_from_features(normalized),
        "total": len(features),
        "order_policy": {
            "source": "locked_canonical_36",
            "locked_feature_count": len(LOCKED_CANONICAL_FEATURE_IDS),
            "canonical_order_version": CANONICAL_ORDER_VERSION,
        },
    }


@router.get("/features/registry/all")
async def get_all_features(request: Request):
    """Admin: Get ALL features including disabled ones."""
    from routes.db import require_admin

    await require_admin(request)
    return await _build_all_features_admin_payload()


@router.get("/features/canonical-audit")
async def get_canonical_audit(request: Request):
    """Admin read-only canonical order drift audit for observability dashboards."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()
    return await _build_canonical_audit_payload(db)


def _canonical_manifest_download_response() -> Response:
    payload = _build_canonical_order_manifest_payload()
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="canonical_order_manifest.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/features/canonical-order-manifest")
async def download_canonical_order_manifest(request: Request):
    """Admin download endpoint for canonical_order_manifest.json."""
    from routes.db import require_admin

    await require_admin(request)
    return _canonical_manifest_download_response()


@router.get("/features/canonical-order-manifest.json")
async def download_canonical_order_manifest_json(request: Request):
    """Admin JSON filename alias for canonical order manifest download."""
    from routes.db import require_admin

    await require_admin(request)
    return _canonical_manifest_download_response()


@router.get("/admin/features/registry/all")
async def get_all_features_admin_alias(request: Request):
    """Admin compatibility alias for tools expecting /api/admin/features/registry/all."""
    from routes.db import require_admin

    await require_admin(request)
    return await _build_all_features_admin_payload()


@router.get("/admin/features/lifecycle-audit")
async def get_feature_lifecycle_audit(request: Request):
    """Admin: Feature lifecycle traceability from live registry and audit collections."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()

    retired_rows = await db.feature_registry.find(
        {
            "$or": [
                {"enabled": False},
                {"status": "retired"},
                {"availability": "retired"},
                {"retired_phase": {"$exists": True}},
            ]
        },
        {
            "_id": 0,
            "feature_id": 1,
            "title": 1,
            "category": 1,
            "route": 1,
            "enabled": 1,
            "status": 1,
            "availability": 1,
            "retired_phase": 1,
            "retired_reason": 1,
            "retired_at": 1,
            "updated_at": 1,
            "replacement_routes": 1,
        },
    ).sort("retired_at", -1).to_list(500)

    retired_features = []
    for row in retired_rows:
        feature_id = str(row.get("feature_id") or "").strip()
        replacement_routes = row.get("replacement_routes") or {}
        replacement_route = replacement_routes.get(feature_id) if isinstance(replacement_routes, dict) else None
        retired_features.append(
            {
                "feature_id": feature_id,
                "title": row.get("title"),
                "category": row.get("category"),
                "route": row.get("route"),
                "replacement_route": replacement_route,
                "enabled": bool(row.get("enabled", False)),
                "status": row.get("status") or row.get("availability") or "retired",
                "retired_phase": row.get("retired_phase") or "legacy",
                "retired_reason": row.get("retired_reason") or "Retired from user-facing feature catalog.",
                "retired_at": row.get("retired_at") or row.get("updated_at"),
                "updated_at": row.get("updated_at"),
            }
        )

    audit_events = await db.phase_f_feature_cleanup_audit.find(
        {},
        {
            "_id": 0,
            "phase": 1,
            "phase_step": 1,
            "name": 1,
            "removed_feature_ids": 1,
            "total_phase_f_retired_feature_ids": 1,
            "policy": 1,
            "root_cause": 1,
            "feature_registry_modified": 1,
            "active_feature_count_before": 1,
            "active_feature_count_after": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(10).to_list(10)

    platform_events = await db.global_platform_events.find(
        {"metadata.removed_feature_ids": {"$exists": True}},
        {
            "_id": 0,
            "event_id": 1,
            "event_type": 1,
            "what_changed": 1,
            "why_changed": 1,
            "impact": 1,
            "metadata": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(10).to_list(10)

    active_count = await db.feature_registry.count_documents({"enabled": {"$ne": False}})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_features": int(active_count),
            "retired_features": len(retired_features),
            "latest_phase": retired_features[0].get("retired_phase") if retired_features else None,
        },
        "retired_features": retired_features,
        "audit_events": audit_events,
        "platform_events": platform_events,
    }


@router.get("/admin/features/retirement-phase1/candidates")
async def get_feature_retirement_phase1_candidates(request: Request):
    """Admin: Live usage-based candidates for safe Phase 1 UI hide rollout."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()

    now = datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).replace(microsecond=0).isoformat()
    cutoff_90 = (now - timedelta(days=90)).replace(microsecond=0).isoformat()

    usage_30, usage_90, last_used_at = await _collect_usage_windows(db, cutoff_30, cutoff_90)

    features = await db.feature_registry.find(
        {"enabled": True},
        {
            "_id": 0,
            "feature_id": 1,
            "title": 1,
            "category": 1,
            "route": 1,
            "premium": 1,
            "soft_deactivated": 1,
            "soft_deactivated_at": 1,
            "soft_deactivation_reason": 1,
            "sort_order": 1,
            "updated_at": 1,
        },
    ).sort("sort_order", 1).to_list(1000)

    rows = []
    for feature in features:
        feature_id = str(feature.get("feature_id") or "").strip()
        if not feature_id:
            continue

        c30 = int(usage_30.get(feature_id, 0) or 0)
        c90 = int(usage_90.get(feature_id, 0) or 0)
        is_soft_hidden = bool(feature.get("soft_deactivated", False))

        candidate_reason = None
        priority = "healthy"
        if c90 == 0 and not is_soft_hidden:
            candidate_reason = "No usage detected in last 90 days. Safe candidate for Phase 1 UI hide."
            priority = "high"
        elif c30 <= 1 and c90 <= 3 and not is_soft_hidden:
            candidate_reason = "Very low usage in last 30/90 days. Review for Phase 1 UI hide."
            priority = "medium"

        rows.append(
            {
                **feature,
                "usage_30d": c30,
                "usage_90d": c90,
                "last_used_at": last_used_at.get(feature_id),
                "phase1_candidate": bool(candidate_reason),
                "phase1_candidate_priority": priority,
                "phase1_candidate_reason": candidate_reason,
            }
        )

    rows.sort(key=lambda row: (bool(row.get("soft_deactivated")), row.get("usage_90d", 0), row.get("usage_30d", 0), row.get("sort_order", 9999)))
    candidates = [row for row in rows if row.get("phase1_candidate")]

    return {
        "generated_at": now.isoformat(),
        "usage_windows": {"days_30": cutoff_30, "days_90": cutoff_90},
        "summary": {
            "total_enabled_features": len(rows),
            "soft_hidden_features": len([r for r in rows if r.get("soft_deactivated")]),
            "phase1_candidates": len(candidates),
            "high_priority_candidates": len([r for r in candidates if r.get("phase1_candidate_priority") == "high"]),
        },
        "candidates": candidates,
        "features": rows,
    }


@router.get("/admin/features/retirement-phase2/candidates")
async def get_feature_retirement_phase2_candidates(request: Request):
    """Admin: Live validation feed for Phase 2 registry deactivation candidates."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()

    now = datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).replace(microsecond=0).isoformat()
    cutoff_90 = (now - timedelta(days=90)).replace(microsecond=0).isoformat()
    usage_30, usage_90, last_used_at = await _collect_usage_windows(db, cutoff_30, cutoff_90)

    features = await db.feature_registry.find(
        {},
        {
            "_id": 0,
            "feature_id": 1,
            "title": 1,
            "category": 1,
            "route": 1,
            "premium": 1,
            "enabled": 1,
            "status": 1,
            "availability": 1,
            "soft_deactivated": 1,
            "soft_deactivated_at": 1,
            "soft_deactivation_reason": 1,
            "phase2_deactivated": 1,
            "retired_phase": 1,
            "retired_at": 1,
            "sort_order": 1,
            "updated_at": 1,
        },
    ).sort("sort_order", 1).to_list(1200)

    rows = []
    for feature in features:
        feature_id = str(feature.get("feature_id") or "").strip()
        if not feature_id:
            continue
        rows.append(
            _build_phase2_retirement_row(
                feature=feature,
                usage_30=usage_30,
                usage_90=usage_90,
                last_used_at=last_used_at,
                now=now,
            )
        )

    rows.sort(
        key=lambda row: (
            not bool(row.get("phase2_candidate")),
            bool(row.get("phase2_deactivated")),
            row.get("usage_90d", 0),
            row.get("usage_30d", 0),
            row.get("sort_order", 9999),
        )
    )
    candidates = [row for row in rows if row.get("phase2_candidate")]

    return {
        "generated_at": now.isoformat(),
        "usage_windows": {"days_30": cutoff_30, "days_90": cutoff_90},
        "summary": {
            "total_features": len(rows),
            "phase2_candidates": len(candidates),
            "phase2_retired": len([r for r in rows if r.get("phase2_deactivated")]),
            "blocked_candidates": len([r for r in rows if not r.get("phase2_candidate") and not r.get("phase2_deactivated")]),
        },
        "candidates": candidates,
        "features": rows,
    }


@router.post("/admin/features/registry/{feature_id}/phase1-soft-hide")
async def phase1_soft_hide_feature(feature_id: str, request: Request, body: Phase1SoftHideRequest):
    """Admin: Soft-hide a feature from user-facing UI without hard deletion."""
    from routes.db import require_admin

    user = await require_admin(request)
    db = await _get_db()

    existing = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "soft_deactivated": True,
        "soft_deactivation_phase": "phase1_safe_ui_hide",
        "soft_deactivation_source": "admin_feature_retirement",
        "soft_deactivated_at": now,
        "soft_deactivated_by": getattr(user, "user_id", ""),
        "soft_deactivation_reason": body.reason or "Phase 1 safe retirement (UI hidden)",
        "soft_deactivation_tag": body.retirement_tag or "phase1_safe_ui_hide",
        "updated_at": now,
    }

    await db.feature_registry.update_one({"feature_id": feature_id}, {"$set": updates})
    _registry_cache["ts"] = 0

    from utils.ws_manager import broadcast_data_change

    await broadcast_data_change("features", "updated")
    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason=f"Feature soft-hidden in Phase 1: {feature_id}",
            actor_user_id=getattr(user, "user_id", ""),
            event_type="FeatureUpdated",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (phase1-soft-hide): {exc}")

    updated = _normalize_feature_payload(await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0}))
    return {"status": "soft_hidden", "feature": updated}


@router.post("/admin/features/registry/{feature_id}/phase1-restore")
async def phase1_restore_feature(feature_id: str, request: Request, body: Phase1RestoreRequest):
    """Admin: Restore a Phase-1 soft-hidden feature to user-facing UI."""
    from routes.db import require_admin

    user = await require_admin(request)
    db = await _get_db()

    existing = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "soft_deactivated": False,
        "soft_restored_at": now,
        "soft_restored_by": getattr(user, "user_id", ""),
        "soft_restore_reason": body.reason or "Phase 1 soft retirement restored",
        "updated_at": now,
    }

    await db.feature_registry.update_one({"feature_id": feature_id}, {"$set": updates})
    _registry_cache["ts"] = 0

    from utils.ws_manager import broadcast_data_change

    await broadcast_data_change("features", "updated")
    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason=f"Feature restored from Phase 1 soft hide: {feature_id}",
            actor_user_id=getattr(user, "user_id", ""),
            event_type="FeatureUpdated",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (phase1-restore): {exc}")

    updated = _normalize_feature_payload(await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0}))
    return {"status": "restored", "feature": updated}


@router.post("/admin/features/registry/{feature_id}/phase2-deactivate")
async def phase2_deactivate_feature(feature_id: str, request: Request, body: Phase2DeactivateRequest):
    """Admin: Perform Phase 2 registry deactivation after usage validation checks."""
    from routes.db import require_admin

    user = await require_admin(request)
    db = await _get_db()

    existing = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    cutoff_30 = (now_dt - timedelta(days=30)).replace(microsecond=0).isoformat()
    cutoff_90 = (now_dt - timedelta(days=90)).replace(microsecond=0).isoformat()
    usage_30, usage_90, last_used_at = await _collect_usage_windows(db, cutoff_30, cutoff_90)
    phase2_row = _build_phase2_retirement_row(
        feature=existing,
        usage_30=usage_30,
        usage_90=usage_90,
        last_used_at=last_used_at,
        now=now_dt,
    )

    blockers = [str(item) for item in (phase2_row.get("phase2_blockers") or [])]
    min_days = int(body.minimum_soft_hidden_days or 0)
    if int(phase2_row.get("soft_hidden_days") or 0) < min_days:
        blockers.append(f"Soft-hide soak period must be at least {min_days} day(s).")

    if blockers:
        raise HTTPException(status_code=409, detail=f"Phase 2 validation failed: {' '.join(blockers)}")

    updates = {
        "enabled": False,
        "status": "retired",
        "availability": "retired",
        "phase2_deactivated": True,
        "retired_phase": "phase2_registry_deactivation",
        "retired_reason": body.reason or "Phase 2 retirement (registry deactivated)",
        "retired_at": now,
        "retired_by": getattr(user, "user_id", ""),
        "phase2_retirement_tag": body.retirement_tag or "phase2_registry_deactivation",
        "phase2_last_validated_usage": {
            "usage_30d": int(phase2_row.get("usage_30d") or 0),
            "usage_90d": int(phase2_row.get("usage_90d") or 0),
            "last_used_at": phase2_row.get("last_used_at"),
            "soft_hidden_days": int(phase2_row.get("soft_hidden_days") or 0),
            "validated_at": now,
        },
        "updated_at": now,
    }

    await db.feature_registry.update_one({"feature_id": feature_id}, {"$set": updates})
    _registry_cache["ts"] = 0

    from utils.ws_manager import broadcast_data_change

    await broadcast_data_change("features", "updated")
    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason=f"Feature retired in Phase 2: {feature_id}",
            actor_user_id=getattr(user, "user_id", ""),
            event_type="FeatureUpdated",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (phase2-deactivate): {exc}")

    updated = _normalize_feature_payload(await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0}))
    return {"status": "phase2_retired", "feature": updated}


@router.post("/admin/features/registry/{feature_id}/phase2-restore")
async def phase2_restore_feature(feature_id: str, request: Request, body: Phase2RestoreRequest):
    """Admin: Restore a Phase 2 retired feature back to active registry state."""
    from routes.db import require_admin

    user = await require_admin(request)
    db = await _get_db()

    existing = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "enabled": True,
        "status": "active",
        "availability": "active",
        "soft_deactivated": False,
        "soft_restored_at": now,
        "soft_restored_by": getattr(user, "user_id", ""),
        "soft_restore_reason": body.reason or "Phase 2 retirement restored by admin",
        "phase2_deactivated": False,
        "phase2_restored_at": now,
        "phase2_restored_by": getattr(user, "user_id", ""),
        "phase2_restore_reason": body.reason or "Phase 2 retirement restored by admin",
        "updated_at": now,
    }
    unset_fields = {
        "retired_phase": "",
        "retired_reason": "",
        "retired_at": "",
        "retired_by": "",
        "phase2_retirement_tag": "",
        "phase2_last_validated_usage": "",
    }

    await db.feature_registry.update_one({"feature_id": feature_id}, {"$set": updates, "$unset": unset_fields})
    _registry_cache["ts"] = 0

    from utils.ws_manager import broadcast_data_change

    await broadcast_data_change("features", "updated")
    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason=f"Feature restored from Phase 2 retirement: {feature_id}",
            actor_user_id=getattr(user, "user_id", ""),
            event_type="FeatureUpdated",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (phase2-restore): {exc}")

    updated = _normalize_feature_payload(await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0}))
    return {"status": "phase2_restored", "feature": updated}


# ── Admin CRUD ────────────────────────────────────────────────────────────────


@router.post("/admin/features/registry")
async def create_feature(request: Request):
    """Admin: Add a new feature to the registry."""
    from routes.db import require_admin
    user = await require_admin(request)

    body = await request.json()
    db = await _get_db()

    feature_id = body.get("feature_id") or body.get("id")
    if not feature_id:
        raise HTTPException(status_code=400, detail="feature_id is required")

    existing = await db.feature_registry.find_one({"feature_id": feature_id})
    if existing:
        raise HTTPException(status_code=409, detail=f"Feature '{feature_id}' already exists")

    now = datetime.now(timezone.utc).isoformat()
    max_order = await db.feature_registry.find_one(
        {}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)]
    )
    next_order = (max_order["sort_order"] + 1) if max_order and "sort_order" in max_order else 0

    feature = {
        "feature_id": feature_id,
        "title": body.get("title", feature_id),
        "description": body.get("description", ""),
        "icon": body.get("icon", "apps"),
        "route": body.get("route", f"/features/{feature_id}"),
        "category": body.get("category", "productivity"),
        "color": _normalize_feature_color(body.get("color", "#14B8A6")),
        "is_new": body.get("is_new", True),
        "premium": body.get("premium", False),
        "enabled": body.get("enabled", True),
        "sort_order": body.get("sort_order", next_order),
        "created_at": now,
        "updated_at": now,
    }

    await db.feature_registry.insert_one(feature)
    feature = _normalize_feature_payload(feature)
    _registry_cache["ts"] = 0  # invalidate cache

    # Broadcast real-time update
    from utils.ws_manager import broadcast_data_change
    await broadcast_data_change("features", "created")
    try:
        from routes.global_platform_state import sync_global_features
        await sync_global_features(reason="FeatureAdded via admin registry", actor_user_id=user.user_id, event_type="FeatureAdded")
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (create): {exc}")

    logger.info(f"Feature created: {feature_id}")
    return {"status": "created", "feature": feature}


@router.put("/admin/features/registry/{feature_id}")
async def update_feature(feature_id: str, request: Request):
    """Admin: Update a feature in the registry."""
    from routes.db import require_admin

    user = await require_admin(request)
    body = await request.json()
    db = await _get_db()

    existing = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    now = datetime.now(timezone.utc).isoformat()
    allowed_fields = {
        "title",
        "description",
        "icon",
        "route",
        "category",
        "color",
        "is_new",
        "premium",
        "enabled",
        "sort_order",
        "feature_number",
        "feature_batch",
    }

    updates = {k: v for k, v in body.items() if k in allowed_fields}
    if "color" in updates:
        updates["color"] = _normalize_feature_color(str(updates.get("color") or "#14B8A6"))
    updates["updated_at"] = now

    await db.feature_registry.update_one({"feature_id": feature_id}, {"$set": updates})
    _registry_cache["ts"] = 0

    from utils.ws_manager import broadcast_data_change

    await broadcast_data_change("features", "updated")
    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason=f"FeatureUpdated via admin registry: {feature_id}",
            actor_user_id=user.user_id,
            event_type="FeatureUpdated",
        )
    except Exception as exc:
        logger.warning(f"GPS feature sync warning (update): {exc}")

    updated = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0})
    return {"status": "updated", "feature": _normalize_feature_payload(updated or {})}


@router.delete("/admin/features/registry/{feature_id}")
async def delete_feature(feature_id: str, request: Request):
    """Admin: Delete a feature from registry."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()

    existing = await db.feature_registry.find_one({"feature_id": feature_id}, {"_id": 0, "feature_id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    await db.feature_registry.delete_one({"feature_id": feature_id})
    _registry_cache["ts"] = 0

    from utils.ws_manager import broadcast_data_change

    await broadcast_data_change("features", "deleted")
    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason=f"FeatureDeleted via admin registry: {feature_id}"
        )
    except Exception:
        pass
    return {"status": "deleted", "feature_id": feature_id}