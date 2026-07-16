"""
Travel Visa → Daily Meditation
Enterprise-grade faith-centered reflection, companion insights, reminders, and progress.
"""

import csv
import io
import json
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes import db as db_module
from routes.db import User, require_admin, require_auth
from utils.access_control_engine import compute_effective_plan
from utils.pagination import iter_find_paginated

router = APIRouter(prefix="/travel-visa/daily-meditation", tags=["travel-visa-daily-meditation"])

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")


def get_db():
    return db_module.db


MEDITATION_FEATURES = [
    {"feature_id": "heart_checkin", "label": "Heart Check-In", "tier": "free"},
    {"feature_id": "gentle_companion", "label": "Gentle Companion Chat", "tier": "free"},
    {"feature_id": "mind_body_pattern_prompts", "label": "Mind/Body Pattern Prompts", "tier": "free"},
    {"feature_id": "daily_gifts", "label": "Daily Gifts", "tier": "free"},
    {"feature_id": "two_min_scripture", "label": "2-Minute Scripture", "tier": "free"},
    {"feature_id": "guided_reflections", "label": "Guided Reflections", "tier": "free"},
    {"feature_id": "embodied_practice", "label": "Optional Embodied Practice", "tier": "free"},
    {"feature_id": "somatic_invitations", "label": "Somatic Invitations", "tier": "free"},
    {"feature_id": "calming_breathwork", "label": "Calming Breathwork", "tier": "free"},
    {"feature_id": "private_prayer_journal", "label": "Private Prayer Journal", "tier": "basic"},
    {"feature_id": "private_reflection_vault", "label": "Private Reflection Vault", "tier": "basic"},
    {"feature_id": "community_care", "label": "Community Care Feed", "tier": "basic"},
    {"feature_id": "prayer_support_loop", "label": "Prayer Support Loop", "tier": "basic"},
    {"feature_id": "lookback_timeline", "label": "Weekly/Monthly Look Back", "tier": "free"},
    {"feature_id": "calm_mode_design", "label": "Calm Mode (No-Pressure UX)", "tier": "free"},
    {"feature_id": "ai_theme_insights", "label": "AI Theme Insights", "tier": "basic"},
    {"feature_id": "personalized_journey_plans", "label": "Personalized Journey Plans", "tier": "basic"},
    {"feature_id": "smart_reminders", "label": "Smart Reminder Engine", "tier": "basic"},
    {"feature_id": "compassionate_progress", "label": "Compassionate Progress", "tier": "free"},
    {"feature_id": "wellbeing_guardrails", "label": "Wellbeing Risk Guardrails", "tier": "free"},
    {"feature_id": "v2_theme_mode", "label": "V2 Light/Dark Support", "tier": "free"},
    {"feature_id": "i18n_ready_content", "label": "Global i18n-ready Content", "tier": "free"},
    {"feature_id": "ai_entitlement_guard", "label": "AI-Driven Entitlement Guard", "tier": "free"},
    {"feature_id": "community_moderation_tools", "label": "Community Moderation Hooks", "tier": "premium"},
    {"feature_id": "audit_export_pack", "label": "Audit/Compliance Export Pack", "tier": "premium"},
    {"feature_id": "prayer_audio_library_150_categories", "label": "Prayer Audio Library (150 Categories)", "tier": "free"},
    {"feature_id": "animated_prayer_visuals", "label": "Animated Prayer Visual Experience", "tier": "basic"},
    {"feature_id": "daily_three_audio_auto_drop", "label": "Daily Auto-Drop (3 New Prayer Audios)", "tier": "basic"},
    {"feature_id": "audio_drop_notifications", "label": "Prayer Audio In-App + Email Notifications", "tier": "basic"},
    {"feature_id": "audio_player_personalization", "label": "Prayer Audio Player Personalization", "tier": "premium"},
    {"feature_id": "prayer_audio_completion_funnels", "label": "Prayer Audio Completion Funnels + Cohort Analytics", "tier": "basic"},
    {"feature_id": "prayer_audio_semantic_search", "label": "Prayer Audio Semantic Search (Intent + Scripture + Mood)", "tier": "basic"},
    {"feature_id": "prayer_audio_upgrade_attribution_by_category", "label": "Prayer Audio Upgrade Attribution by Category", "tier": "basic"},
]


MEDITATION_LIMITS = {
    "free": {
        "daily_checkins": 2,
        "daily_journal_entries": 2,
        "daily_ai_companion": 2,
        "daily_ai_insights": 1,
        "daily_somatic_sessions": 3,
        "daily_audio_plays": 5,
        "weekly_community_posts": 0,
        "monthly_exports": 1,
    },
    "basic": {
        "daily_checkins": 40,
        "daily_journal_entries": 40,
        "daily_ai_companion": 40,
        "daily_ai_insights": 20,
        "daily_somatic_sessions": 25,
        "daily_audio_plays": 80,
        "weekly_community_posts": 30,
        "monthly_exports": 20,
    },
    "premium": {
        "daily_checkins": 999,
        "daily_journal_entries": 999,
        "daily_ai_companion": 999,
        "daily_ai_insights": 999,
        "daily_somatic_sessions": 999,
        "daily_audio_plays": 999,
        "weekly_community_posts": 999,
        "monthly_exports": 999,
    },
}


def _scope_label(plan: str) -> str:
    if plan == "premium":
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


PRAYER_AUDIO_BASE_CATEGORIES = [
    "Morning Gratitude",
    "Evening Surrender",
    "Anxiety Relief",
    "Peace & Stillness",
    "Healing & Recovery",
    "Family & Marriage",
    "Parenting Wisdom",
    "Financial Provision",
    "Work & Career",
    "Students & Exams",
    "Strength in Trials",
    "Hope in Waiting",
    "Forgiveness",
    "Guidance & Discernment",
    "Protection & Safety",
    "Deliverance & Freedom",
    "Leadership & Service",
    "Community & Unity",
    "Nation & Governance",
    "Missions & Compassion",
    "Sleep & Rest",
    "Joy & Celebration",
    "Grief & Comfort",
    "New Beginnings",
    "Thanksgiving & Testimony",
]

PRAYER_AUDIO_CATEGORY_SUFFIXES = [
    "for Students",
    "for Professionals",
    "for Families",
    "for Leaders",
    "for Recovery",
]

PRAYER_AUDIO_CATEGORIES = PRAYER_AUDIO_BASE_CATEGORIES + [
    f"{base} · {suffix}"
    for base in PRAYER_AUDIO_BASE_CATEGORIES
    for suffix in PRAYER_AUDIO_CATEGORY_SUFFIXES
]

PRAYER_AUDIO_LIBRARY_TARGET = 600

PRAYER_AUDIO_SOURCE_URLS = [
    *[f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3" for i in range(1, 11)],
    "https://www.learningcontainer.com/wp-content/uploads/2020/02/Kalimba.mp3",
    "https://www.learningcontainer.com/wp-content/uploads/2020/02/Temple-Of-The-King.mp3",
    "https://archive.org/download/ifigeniaenaulide_2605_librivox/ifigeniaenaulide_01_euripides.mp3",
    "https://archive.org/download/ifigeniaenaulide_2605_librivox/ifigeniaenaulide_02_euripides.mp3",
]

PRAYER_IMAGE_URLS = [
    "https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?auto=format&fit=crop&w=1600&q=80",
    "https://images.unsplash.com/photo-1506126613408-eca07ce68773?auto=format&fit=crop&w=1600&q=80",
    "https://images.unsplash.com/photo-1504052434569-70ad5836ab65?auto=format&fit=crop&w=1600&q=80",
    "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1600&q=80",
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&q=80",
    "https://images.unsplash.com/photo-1465101046530-73398c7f28ca?auto=format&fit=crop&w=1600&q=80",
]

PRAYER_ANIMATION_PRESETS = [
    {"preset": "soft-glow", "duration_ms": 6000, "overlay": "#14B8A6"},
    {"preset": "gentle-parallax", "duration_ms": 7000, "overlay": "#22C55E"},
    {"preset": "particle-drift", "duration_ms": 8000, "overlay": "#38BDF8"},
    {"preset": "scripture-fade", "duration_ms": 6500, "overlay": "#F59E0B"},
]

PRAYER_INTENT_SIGNALS = {
    "peace": ["peace", "stillness", "calm", "rest", "surrender", "quiet"],
    "healing": ["healing", "recovery", "restore", "mercy", "comfort"],
    "guidance": ["guidance", "discernment", "wisdom", "direction", "light"],
    "provision": ["provision", "financial", "work", "career", "daily bread"],
    "family": ["family", "marriage", "parenting", "children", "home"],
    "protection": ["protection", "safety", "deliverance", "freedom", "shield"],
    "strength": ["strength", "trials", "endurance", "hope", "persevere"],
    "gratitude": ["gratitude", "thanksgiving", "testimony", "joy", "celebration"],
}

PRAYER_MOOD_SIGNALS = {
    "anxious": ["peace", "protection"],
    "overwhelmed": ["strength", "guidance"],
    "tired": ["peace", "healing"],
    "grateful": ["gratitude"],
    "hopeful": ["strength", "guidance"],
    "sad": ["healing", "peace"],
    "fearful": ["protection", "peace"],
}


DAILY_GIFTS = [
    {
        "gift_id": "gift_hope_1",
        "title": "A Quiet Start",
        "scripture": "Psalm 46:10 — Be still, and know that I am God.",
        "reflection": "What part of your day needs stillness more than speed?",
        "practice": "Inhale for 4, hold for 4, exhale for 6. Repeat 4 rounds.",
    },
    {
        "gift_id": "gift_peace_2",
        "title": "Peace Over Pressure",
        "scripture": "Philippians 4:6-7 — Present your requests to God... and the peace of God will guard your heart.",
        "reflection": "Name one burden you can release for today.",
        "practice": "Ground your feet for 90 seconds and soften your shoulders.",
    },
    {
        "gift_id": "gift_grace_3",
        "title": "Grace for This Moment",
        "scripture": "2 Corinthians 12:9 — My grace is sufficient for you.",
        "reflection": "Where do you need grace instead of self-judgment?",
        "practice": "Hand-on-heart breathing for 2 minutes.",
    },
    {
        "gift_id": "gift_strength_4",
        "title": "Steady Strength",
        "scripture": "Isaiah 41:10 — Do not fear, for I am with you.",
        "reflection": "What fear can you name honestly today?",
        "practice": "Box breathing (4-4-4-4) for 2 minutes.",
    },
    {
        "gift_id": "gift_light_5",
        "title": "Guided Light",
        "scripture": "Psalm 119:105 — Your word is a lamp to my feet.",
        "reflection": "What is your next faithful small step?",
        "practice": "Slow walk for 3 minutes with mindful breathing.",
    },
    {
        "gift_id": "gift_mercy_6",
        "title": "Morning Mercy",
        "scripture": "Lamentations 3:22-23 — His mercies are new every morning.",
        "reflection": "What can begin again today without shame?",
        "practice": "Write one sentence of gratitude and sit in silence for 60 seconds.",
    },
    {
        "gift_id": "gift_rest_7",
        "title": "Rest for the Soul",
        "scripture": "Matthew 11:28 — Come to me, all who are weary.",
        "reflection": "What would rest look like in your next hour?",
        "practice": "Neck/shoulder release + 5 slow breaths.",
    },
]


SOMATIC_INVITATIONS = [
    {"invitation_id": "somatic_01", "title": "Grounding Breath", "duration_sec": 120, "goal": "Settle racing thoughts"},
    {"invitation_id": "somatic_02", "title": "Release Shoulders", "duration_sec": 90, "goal": "Lower physical tension"},
    {"invitation_id": "somatic_03", "title": "Body Scan Prayer", "duration_sec": 180, "goal": "Notice where stress sits"},
    {"invitation_id": "somatic_04", "title": "Slow Exhale Reset", "duration_sec": 150, "goal": "Downshift nervous system"},
    {"invitation_id": "somatic_05", "title": "Compassion Posture", "duration_sec": 120, "goal": "Restore emotional safety"},
    {"invitation_id": "somatic_06", "title": "Evening Calm", "duration_sec": 240, "goal": "Prepare body for rest"},
]


HIGH_RISK_TERMS = {
    "suicide", "self-harm", "harm myself", "kill myself", "end my life", "end everything", "hopeless", "can\u2019t go on", "can't go on",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _week_key(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _safe_parse_iso(value: str) -> Optional[datetime]:
    try:
        if not value:
            return None
        v = str(value).strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        parsed = datetime.fromisoformat(v)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


async def _record_audio_funnel_event(
    db,
    user_id: str,
    event_type: str,
    plan: str,
    audio_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    dedupe_scope: Optional[str] = None,
) -> None:
    now_iso = _iso_now()
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dedupe_key = dedupe_scope or f"{user_id}:{event_type}:{audio_id or 'none'}:{date_key}"

    payload = {
        "event_id": f"dmae_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "event_type": event_type,
        "date_key": date_key,
        "occurred_at": now_iso,
        "dedupe_key": dedupe_key,
        "created_at": now_iso,
    }

    await db.tv_dm_audio_funnel_events.update_one(
        {"dedupe_key": dedupe_key},
        {
            "$set": {
                "plan_at_event": plan,
                "audio_id": audio_id or "",
                "metadata": metadata or {},
                "updated_at": now_iso,
            },
            "$setOnInsert": payload,
        },
        upsert=True,
    )


def _cohort_bucket() -> dict:
    return {
        "drop_opened": 0,
        "played": 0,
        "played_30s": 0,
        "played_75pct": 0,
        "completed": 0,
        "upgraded": 0,
        "play_rate_pct": 0.0,
        "played_30s_rate_pct": 0.0,
        "played_75pct_rate_pct": 0.0,
        "completion_rate_pct": 0.0,
        "upgrade_rate_pct": 0.0,
    }


async def _build_prayer_audio_funnel_analytics(db, days: int = 14, conversion_window_days: int = 14) -> dict:
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=days)
    since_iso = since_dt.isoformat()
    events = await db.tv_dm_audio_funnel_events.find(
        {"occurred_at": {"$gte": since_iso}},
        {"_id": 0},
    ).to_list(60000)

    # Last-touch attribution anchor: latest drop_opened per user in window
    last_open: dict[str, dict] = {}
    for row in events:
        if row.get("event_type") != "drop_opened":
            continue
        uid = str(row.get("user_id") or "")
        when = _safe_parse_iso(str(row.get("occurred_at") or ""))
        if not uid or when is None:
            continue
        prev = last_open.get(uid)
        if not prev or when > prev["occurred_at_dt"]:
            last_open[uid] = {
                "plan": str(row.get("plan_at_event") or "free").lower(),
                "occurred_at_dt": when,
                "occurred_at": row.get("occurred_at"),
            }

    cohorts = {
        "free": _cohort_bucket(),
        "basic": _cohort_bucket(),
        "premium": _cohort_bucket(),
    }

    # Base drop_opened users by last-touch plan
    for uid, info in last_open.items():
        plan = info["plan"] if info["plan"] in cohorts else "free"
        cohorts[plan]["drop_opened"] += 1

    def _qualifies(uid: str, step: str) -> bool:
        anchor = last_open.get(uid)
        if not anchor:
            return False
        anchor_dt = anchor["occurred_at_dt"]
        window_end = anchor_dt + timedelta(days=conversion_window_days)
        for row in events:
            if str(row.get("user_id") or "") != uid:
                continue
            if str(row.get("event_type") or "") != step:
                continue
            step_dt = _safe_parse_iso(str(row.get("occurred_at") or ""))
            if step_dt is None:
                continue
            if anchor_dt <= step_dt <= window_end:
                return True
        return False

    step_keys = ["played", "played_30s", "played_75pct", "completed"]
    for uid, info in last_open.items():
        plan = info["plan"] if info["plan"] in cohorts else "free"
        for step in step_keys:
            if _qualifies(uid, step):
                cohorts[plan][step] += 1

    # Upgrade conversion (Free->Basic/Premium) within conversion window after last drop_opened
    user_ids = list(last_open.keys())
    audit_rows = []
    if user_ids:
        async for row in iter_find_paginated(
            db.subscription_lifecycle_audit,
            {
                "user_id": {"$in": user_ids},
                "action": {"$in": ["upgrade", "plan_change"]},
            },
            {"_id": 0, "user_id": 1, "action": 1, "target_plan": 1, "timestamp": 1, "created_at": 1},
            page_size=1000,
            max_docs=50000,
        ):
            audit_rows.append(row)

    for row in audit_rows:
        uid = str(row.get("user_id") or "")
        anchor = last_open.get(uid)
        if not anchor:
            continue
        ts = str(row.get("timestamp") or row.get("created_at") or "")
        ts_dt = _safe_parse_iso(ts)
        if ts_dt is None:
            continue
        anchor_dt = anchor["occurred_at_dt"]
        if ts_dt < anchor_dt or ts_dt > anchor_dt + timedelta(days=conversion_window_days):
            continue
        target_plan = str(row.get("target_plan") or "").lower()
        if target_plan in {"basic", "premium"}:
            plan = anchor["plan"] if anchor["plan"] in cohorts else "free"
            cohorts[plan]["upgraded"] += 1

    for plan, bucket in cohorts.items():
        opens = max(1, int(bucket["drop_opened"]))
        bucket["play_rate_pct"] = round((bucket["played"] / opens) * 100, 2)
        bucket["played_30s_rate_pct"] = round((bucket["played_30s"] / opens) * 100, 2)
        bucket["played_75pct_rate_pct"] = round((bucket["played_75pct"] / opens) * 100, 2)
        bucket["completion_rate_pct"] = round((bucket["completed"] / opens) * 100, 2)
        bucket["upgrade_rate_pct"] = round((bucket["upgraded"] / opens) * 100, 2)

    totals = _cohort_bucket()
    for key in ["drop_opened", "played", "played_30s", "played_75pct", "completed", "upgraded"]:
        totals[key] = int(sum(cohorts[p][key] for p in cohorts))
    opens = max(1, int(totals["drop_opened"]))
    totals["play_rate_pct"] = round((totals["played"] / opens) * 100, 2)
    totals["played_30s_rate_pct"] = round((totals["played_30s"] / opens) * 100, 2)
    totals["played_75pct_rate_pct"] = round((totals["played_75pct"] / opens) * 100, 2)
    totals["completion_rate_pct"] = round((totals["completed"] / opens) * 100, 2)
    totals["upgrade_rate_pct"] = round((totals["upgraded"] / opens) * 100, 2)

    return {
        "window_days": days,
        "conversion_window_days": conversion_window_days,
        "attribution": "last_touch",
        "funnel_steps": ["drop_opened", "played", "played_30s", "played_75pct", "completed", "upgraded"],
        "cohorts": cohorts,
        "totals": totals,
        "generated_at": _iso_now(),
    }


def _tokenize_lower(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", str(text or "").lower()) if token]


def _semantic_search_score(
    row: dict,
    query_tokens: list[str],
    scripture_tokens: list[str],
    intent_tokens: list[str],
) -> tuple[int, list[str]]:
    title = str(row.get("title") or "").lower()
    category = str(row.get("category") or "").lower()
    scripture = str(row.get("scripture") or "").lower()
    scripture_ref = str(row.get("scripture_ref") or "").lower()
    description = str(row.get("description") or "").lower()
    transcript = str(row.get("transcript") or "").lower()

    score = 0
    reasons: list[str] = []

    for token in query_tokens:
        if token in title:
            score += 7
            reasons.append(f"title:{token}")
        if token in category:
            score += 5
            reasons.append(f"category:{token}")
        if token in description:
            score += 3
            reasons.append(f"description:{token}")
        if token in transcript:
            score += 2
            reasons.append(f"transcript:{token}")
        if token in scripture:
            score += 6
            reasons.append(f"scripture:{token}")

    for token in scripture_tokens:
        if token in scripture_ref:
            score += 9
            reasons.append(f"scripture_ref:{token}")
        elif token in scripture:
            score += 7
            reasons.append(f"scripture:{token}")

    for token in intent_tokens:
        if token in category:
            score += 5
            reasons.append(f"intent:{token}")
        elif token in title:
            score += 4
            reasons.append(f"intent:{token}")
        elif token in description or token in scripture or token in transcript:
            score += 2
            reasons.append(f"intent:{token}")

    if title and query_tokens and all(token in title for token in query_tokens[:2]):
        score += 4
    if scripture_ref and scripture_tokens and any(token in scripture_ref for token in scripture_tokens):
        score += 5

    unique_reasons = list(dict.fromkeys(reasons))[:8]
    return score, unique_reasons


def _normalize_plan(plan_value: str) -> str:
    plan = str(plan_value or "free").strip().lower()
    if plan not in {"free", "basic", "premium"}:
        return "free"
    return plan


async def _build_prayer_audio_upgrade_attribution_by_category(
    db,
    days: int = 30,
    conversion_window_days: int = 14,
    top: int = 20,
) -> dict:
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(days=days)
    since_iso = since_dt.isoformat()

    events = await db.tv_dm_audio_funnel_events.find(
        {"occurred_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "user_id": 1,
            "event_type": 1,
            "occurred_at": 1,
            "plan_at_event": 1,
            "audio_id": 1,
            "metadata": 1,
        },
    ).to_list(90000)

    event_audio_ids = sorted({str(e.get("audio_id") or "") for e in events if str(e.get("audio_id") or "")})
    catalog_rows: list[dict] = []
    if event_audio_ids:
        catalog_rows = await db.tv_dm_prayer_audio_catalog.find(
            {"audio_id": {"$in": event_audio_ids}},
            {"_id": 0, "audio_id": 1, "category": 1},
        ).to_list(5000)
    catalog_map = {str(r.get("audio_id") or ""): str(r.get("category") or "") for r in catalog_rows}

    category_touch_users: dict[str, set[str]] = defaultdict(set)
    events_by_user: dict[str, list[dict]] = defaultdict(list)

    for row in events:
        uid = str(row.get("user_id") or "")
        when = _safe_parse_iso(str(row.get("occurred_at") or ""))
        if not uid or when is None:
            continue

        metadata = row.get("metadata") or {}
        category = str(metadata.get("category") or "").strip()
        if not category:
            categories = metadata.get("categories") or []
            if isinstance(categories, list) and categories:
                category = str(categories[0] or "").strip()
        if not category:
            category = catalog_map.get(str(row.get("audio_id") or ""), "")

        enriched = {
            "user_id": uid,
            "event_type": str(row.get("event_type") or ""),
            "occurred_at_dt": when,
            "plan_at_event": _normalize_plan(str(row.get("plan_at_event") or "free")),
            "category": category,
        }
        events_by_user[uid].append(enriched)

        if category and enriched["event_type"] in {"drop_opened", "played", "played_30s", "played_75pct", "completed"}:
            category_touch_users[category].add(uid)

    for uid in list(events_by_user.keys()):
        events_by_user[uid].sort(key=lambda x: x.get("occurred_at_dt"))

    upgrade_rows = await db.subscription_lifecycle_audit.find(
        {
            "action": {"$in": ["upgrade", "plan_change"]},
            "$or": [
                {"timestamp": {"$gte": since_iso}},
                {"created_at": {"$gte": since_iso}},
            ],
        },
        {"_id": 0, "user_id": 1, "target_plan": 1, "timestamp": 1, "created_at": 1},
    ).to_list(70000)

    step_priority = {
        "completed": 5,
        "played_75pct": 4,
        "played_30s": 3,
        "played": 2,
        "drop_opened": 1,
    }

    category_stats: dict[str, dict] = defaultdict(lambda: {
        "touch_users": set(),
        "upgraded_users": set(),
        "upgrades_to_basic": 0,
        "upgrades_to_premium": 0,
        "source_free": 0,
        "source_basic": 0,
        "source_premium": 0,
    })

    for category, users in category_touch_users.items():
        category_stats[category]["touch_users"] = set(users)

    seen_upgrade_keys: set[str] = set()

    for row in upgrade_rows:
        uid = str(row.get("user_id") or "")
        if not uid or uid not in events_by_user:
            continue
        target_plan = _normalize_plan(str(row.get("target_plan") or ""))
        if target_plan not in {"basic", "premium"}:
            continue
        ts = str(row.get("timestamp") or row.get("created_at") or "")
        upgraded_at = _safe_parse_iso(ts)
        if upgraded_at is None:
            continue

        upgrade_key = f"{uid}:{target_plan}:{upgraded_at.strftime('%Y-%m-%d')}"
        if upgrade_key in seen_upgrade_keys:
            continue
        seen_upgrade_keys.add(upgrade_key)

        window_start = upgraded_at - timedelta(days=conversion_window_days)
        anchor_event: Optional[dict] = None

        for event in events_by_user.get(uid, []):
            event_dt = event.get("occurred_at_dt")
            category = str(event.get("category") or "")
            if not event_dt or not category:
                continue
            if event_dt > upgraded_at or event_dt < window_start:
                continue
            if not anchor_event:
                anchor_event = event
                continue
            if event_dt > anchor_event.get("occurred_at_dt"):
                anchor_event = event
            elif event_dt == anchor_event.get("occurred_at_dt"):
                if step_priority.get(event.get("event_type", ""), 0) > step_priority.get(anchor_event.get("event_type", ""), 0):
                    anchor_event = event

        if not anchor_event:
            continue

        category = str(anchor_event.get("category") or "")
        if not category:
            continue
        source_plan = _normalize_plan(str(anchor_event.get("plan_at_event") or "free"))

        category_stats[category]["upgraded_users"].add(uid)
        if target_plan == "basic":
            category_stats[category]["upgrades_to_basic"] += 1
        if target_plan == "premium":
            category_stats[category]["upgrades_to_premium"] += 1
        category_stats[category][f"source_{source_plan}"] += 1

    rows = []
    all_touch_users: set[str] = set()
    all_upgraded_users: set[str] = set()

    for category, stats in category_stats.items():
        touch_users = stats.get("touch_users", set())
        upgraded_users = stats.get("upgraded_users", set())
        all_touch_users.update(touch_users)
        all_upgraded_users.update(upgraded_users)

        touched_count = len(touch_users)
        upgraded_count = len(upgraded_users)
        rows.append({
            "category": category,
            "touch_users": touched_count,
            "upgraded_users": upgraded_count,
            "upgrades_to_basic": int(stats.get("upgrades_to_basic", 0)),
            "upgrades_to_premium": int(stats.get("upgrades_to_premium", 0)),
            "source_free": int(stats.get("source_free", 0)),
            "source_basic": int(stats.get("source_basic", 0)),
            "source_premium": int(stats.get("source_premium", 0)),
            "upgrade_rate_pct": round((upgraded_count / max(1, touched_count)) * 100, 2),
        })

    rows.sort(key=lambda x: (x.get("upgraded_users", 0), x.get("upgrade_rate_pct", 0), x.get("touch_users", 0)), reverse=True)
    top_rows = rows[:top]

    totals = {
        "distinct_touch_users": len(all_touch_users),
        "distinct_upgraded_users": len(all_upgraded_users),
        "categories_considered": len(rows),
    }

    return {
        "window_days": days,
        "conversion_window_days": conversion_window_days,
        "attribution": "last_touch_category",
        "top": top,
        "category_slices": top_rows,
        "totals": totals,
        "generated_at": _iso_now(),
    }


def _is_admin_actor(actor: User) -> bool:
    return bool(getattr(actor, "is_admin", False))


async def _resolve_scoped_user_id(request: Request, requested_user_id: Optional[str]) -> tuple[User, str]:
    actor = await require_auth(request)
    actor_user_id = str(getattr(actor, "user_id", "") or "").strip()
    target_user_id = str(requested_user_id or actor_user_id).strip()

    if not actor_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if target_user_id != actor_user_id and not _is_admin_actor(actor):
        raise HTTPException(status_code=403, detail="Cannot access another user's Daily Meditation data")

    return actor, target_user_id


async def _get_user_plan(db, user_id: str) -> str:
    user = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "is_admin": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "full_access": 1,
            "subscription_permanent": 1,
        },
    )
    if not user:
        return "free"
    return compute_effective_plan(user)


def _limits_for(plan: str) -> dict:
    return MEDITATION_LIMITS.get(plan, MEDITATION_LIMITS["free"])


async def _check_limit(
    db,
    user_id: str,
    plan: str,
    action_key: str,
    limit_key: str,
    window: Literal["daily", "weekly", "monthly"] = "daily",
) -> dict:
    limits = _limits_for(plan)
    max_allowed = int(limits.get(limit_key, 0))
    now = datetime.now(timezone.utc)
    bucket = now.strftime("%Y-%m-%d")
    if window == "weekly":
        bucket = _week_key(now)
    elif window == "monthly":
        bucket = now.strftime("%Y-%m")

    usage = await db.tv_dm_usage.find_one(
        {"user_id": user_id, "bucket": bucket, "action": action_key, "window": window},
        {"_id": 0, "count": 1},
    )
    current = int((usage or {}).get("count", 0))

    if max_allowed < 999 and current >= max_allowed:
        return {
            "allowed": False,
            "current": current,
            "limit": max_allowed,
            "remaining": 0,
            "window": window,
            "bucket": bucket,
        }

    await db.tv_dm_usage.update_one(
        {"user_id": user_id, "bucket": bucket, "action": action_key, "window": window},
        {
            "$inc": {"count": 1},
            "$set": {"updated_at": _iso_now()},
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )
    return {
        "allowed": True,
        "current": current + 1,
        "limit": max_allowed,
        "remaining": max(0, max_allowed - (current + 1)) if max_allowed < 999 else 999,
        "window": window,
        "bucket": bucket,
    }


async def _create_in_app_notification(db, user_id: str, title: str, message: str, n_type: str, data: Optional[dict] = None) -> None:
    await db.tv_notifications.insert_one(
        {
            "user_id": user_id,
            "type": f"daily_meditation_{n_type}",
            "title": title,
            "message": message,
            "data": data or {},
            "module": "daily_meditation",
            "read": False,
            "created_at": _iso_now(),
        }
    )


async def _email_allowed(db, user_id: str) -> bool:
    prefs = await db.tv_dm_reminder_prefs.find_one({"user_id": user_id}, {"_id": 0, "email_enabled": 1})
    if not prefs:
        return False
    return bool(prefs.get("email_enabled"))


def _plain_text_from_html(html: str) -> str:
    raw = str(html or "")
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


DM_EMAIL_TEMPLATE_MAP = {
    "daily_meditation_reminder": "daily_meditation_reminder",
    "daily_meditation_prayer_audio_drop": "daily_meditation_prayer_audio_drop",
    "daily_meditation_weekly_digest": "daily_meditation_weekly_digest",
}


async def _send_dm_email(
    db,
    user_id: str,
    subject: str,
    body_html: str,
    email_type: str,
    template_payload: Optional[dict] = None,
) -> str:
    if not await _email_allowed(db, user_id):
        return "skipped_prefs"

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    if not user or not user.get("email"):
        return "no_email"

    try:
        from utils.email_service import send_catalog_template

        template_key = DM_EMAIL_TEMPLATE_MAP.get(str(email_type or "").strip(), "daily_meditation_reminder")
        payload = dict(template_payload or {})
        if template_key == "daily_meditation_reminder":
            payload.setdefault("title", str(subject or "Daily Meditation Reminder"))
            payload.setdefault(
                "message",
                _plain_text_from_html(body_html) or "Take a gentle moment to check in and continue your journey.",
            )

        result = await send_catalog_template(
            recipient_email=str(user["email"]),
            template_key=template_key,
            recipient_name="Learner",
            **payload,
        )
        if bool(result.get("success")):
            return "sent"
        return f"failed:{str(result.get('error') or 'unknown')[:120]}"
    except Exception as exc:
        return f"failed:{str(exc)[:120]}"


async def _build_weekly_digest_payload(db, user_id: str, days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    checkins = await db.tv_dm_checkins.find({"user_id": user_id, "created_at": {"$gte": since}}, {"_id": 0}).to_list(500)
    journal = await db.tv_dm_journal.find({"user_id": user_id, "created_at": {"$gte": since}}, {"_id": 0}).to_list(500)
    somatic = await db.tv_dm_somatic_sessions.find({"user_id": user_id, "completed_at": {"$gte": since}}, {"_id": 0}).to_list(500)

    mood_counts = {}
    for c in checkins:
        mood = str(c.get("mood") or "unknown")
        mood_counts[mood] = mood_counts.get(mood, 0) + 1

    top_moods = sorted(mood_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    dominant_theme = top_moods[0][0] if top_moods else "steady"
    seed = abs(hash(f"{user_id}-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"))
    snippets = [
        DAILY_GIFTS[(seed + 0) % len(DAILY_GIFTS)],
        DAILY_GIFTS[(seed + 2) % len(DAILY_GIFTS)],
        DAILY_GIFTS[(seed + 4) % len(DAILY_GIFTS)],
    ]

    stats = {
        "checkins": len(checkins),
        "journal_entries": len(journal),
        "somatic_sessions": len(somatic),
        "dominant_theme": dominant_theme,
    }
    headline = (
        f"In the last {days} days, you logged {stats['checkins']} check-ins, "
        f"{stats['journal_entries']} journal entries, and {stats['somatic_sessions']} somatic practices."
    )
    encouragement = "This is a streakless journey—presence and honesty matter more than perfect consistency."
    from utils.email_templates import build_daily_meditation_weekly_digest_email

    email_tpl = build_daily_meditation_weekly_digest_email(
        days=days,
        dominant_theme=dominant_theme,
        headline=headline,
        encouragement=encouragement,
        snippets=snippets,
        checkins=stats["checkins"],
        journal_entries=stats["journal_entries"],
        somatic_sessions=stats["somatic_sessions"],
    )
    subject = email_tpl.subject
    html = email_tpl.html

    return {
        "days": days,
        "subject": subject,
        "headline": headline,
        "encouragement": encouragement,
        "stats": stats,
        "snippets": snippets,
        "html": html,
    }


def _free_audio_categories() -> set[str]:
    return set(PRAYER_AUDIO_CATEGORIES[:20])


def _audio_category_allowed(plan: str, category: str) -> bool:
    if plan in {"basic", "premium"}:
        return True
    return category in _free_audio_categories()


def _daily_audio_seed(date_key: str) -> int:
    return abs(hash(f"daily-meditation-prayer-audio-{date_key}"))


def _build_prayer_audio_catalog_doc(index: int) -> dict:
    category = PRAYER_AUDIO_CATEGORIES[index % len(PRAYER_AUDIO_CATEGORIES)]
    source_url = PRAYER_AUDIO_SOURCE_URLS[index % len(PRAYER_AUDIO_SOURCE_URLS)]
    image_url = PRAYER_IMAGE_URLS[index % len(PRAYER_IMAGE_URLS)]
    animation = PRAYER_ANIMATION_PRESETS[index % len(PRAYER_ANIMATION_PRESETS)]
    gift = DAILY_GIFTS[index % len(DAILY_GIFTS)]
    category_slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in category).strip("-")[:90]
    scripture_ref = str(gift.get("scripture", "Psalm 46:10")).split("—")[0].strip()

    return {
        "audio_id": f"dm_catalog_audio_{index + 1:04d}",
        "catalog_index": index,
        "category_slug": category_slug,
        "category": category,
        "title": f"{category} Prayer {((index % 4) + 1)}",
        "description": gift.get("reflection", "A gentle guided prayer audio for your day."),
        "scripture": gift.get("scripture", "Psalm 46:10"),
        "scripture_ref": scripture_ref,
        "audio_url": source_url,
        "duration_sec": 150 + ((index % 7) * 30),
        "image_url": image_url,
        "image_animation_enabled": True,
        "animation": {
            "preset": animation.get("preset"),
            "duration_ms": animation.get("duration_ms"),
            "overlay": animation.get("overlay"),
            "loop": True,
        },
        "transcript": (
            f"Take a deep breath. Reflect on {gift.get('scripture', 'Psalm 46:10')} and receive calm guidance."
        ),
        "license_type": "public_open_audio_demo",
        "license_source": source_url,
        "status": "active",
        "is_catalog": True,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }


async def _ensure_prayer_audio_catalog_seeded(db, min_items: int = PRAYER_AUDIO_LIBRARY_TARGET) -> dict:
    existing_count = await db.tv_dm_prayer_audio_catalog.count_documents({})
    if existing_count >= min_items:
        return {"seeded": False, "before": existing_count, "after": existing_count}

    docs = []
    for idx in range(existing_count, min_items):
        docs.append(_build_prayer_audio_catalog_doc(idx))

    if docs:
        await db.tv_dm_prayer_audio_catalog.insert_many(docs)

    after_count = await db.tv_dm_prayer_audio_catalog.count_documents({})
    return {"seeded": True, "before": existing_count, "after": after_count}


def _build_daily_drop_doc_from_catalog(date_key: str, slot: int, catalog_doc: dict) -> dict:
    return {
        "audio_id": f"dm_drop_{date_key.replace('-', '')}_{slot}",
        "source_audio_id": str(catalog_doc.get("audio_id") or ""),
        "published_date": date_key,
        "slot": slot,
        "category": catalog_doc.get("category"),
        "category_slug": catalog_doc.get("category_slug", ""),
        "title": catalog_doc.get("title"),
        "description": catalog_doc.get("description"),
        "scripture": catalog_doc.get("scripture"),
        "scripture_ref": catalog_doc.get("scripture_ref"),
        "audio_url": catalog_doc.get("audio_url"),
        "duration_sec": int(catalog_doc.get("duration_sec") or 180),
        "image_url": catalog_doc.get("image_url"),
        "image_animation_enabled": bool(catalog_doc.get("image_animation_enabled", True)),
        "animation": catalog_doc.get("animation") or {},
        "transcript": catalog_doc.get("transcript", ""),
        "status": "active",
        "updated_at": _iso_now(),
    }


async def _dispatch_prayer_audio_drop_notifications(db, date_key: str, items: list[dict], max_users: int = 600) -> dict:
    users = await db.tv_dm_reminder_prefs.find(
        {
            "$or": [
                {"in_app_enabled": True},
                {"email_enabled": True},
            ]
        },
        {"_id": 0, "user_id": 1, "in_app_enabled": 1, "email_enabled": 1},
    ).limit(max_users).to_list(max_users)

    in_app_sent = 0
    email_sent = 0
    email_skipped = 0
    categories = [str(i.get("category") or "Prayer") for i in items]
    title = "3 new animated prayer audios are ready"
    message = f"Today's drop is live: {', '.join(categories[:3])}. Tap to listen in Daily Meditation."

    for row in users:
        user_id = str(row.get("user_id") or "")
        if not user_id:
            continue
        if bool(row.get("in_app_enabled", True)):
            await _create_in_app_notification(
                db,
                user_id,
                title,
                message,
                "prayer_audio_daily_drop",
                {"published_date": date_key, "audio_ids": [it.get("audio_id") for it in items[:3]]},
            )
            in_app_sent += 1

        if bool(row.get("email_enabled", False)):
            email_status = await _send_dm_email(
                db,
                user_id,
                f"Daily Meditation · 3 new prayer audios ({date_key})",
                message,
                "daily_meditation_prayer_audio_drop",
                template_payload={
                    "date_key": date_key,
                    "title": title,
                    "message": message,
                    "categories": categories[:3],
                    "items": [
                        {
                            "title": str(it.get("title") or "Prayer Audio"),
                            "scripture": str(it.get("scripture") or ""),
                        }
                        for it in items[:3]
                    ],
                },
            )
            if str(email_status).startswith("sent") or email_status == "sent":
                email_sent += 1
            else:
                email_skipped += 1

    return {
        "users_scanned": len(users),
        "in_app_sent": in_app_sent,
        "email_sent": email_sent,
        "email_skipped": email_skipped,
    }


async def run_daily_prayer_audio_auto_publish(force: bool = False, max_users: int = 600, notify_users: bool = True):
    db = get_db()
    seed_info = await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = await db.tv_dm_prayer_audio.find({"published_date": date_key}, {"_id": 0}).sort("slot", 1).to_list(20)

    created_docs: list[dict] = []
    if force:
        await db.tv_dm_prayer_audio.delete_many({"published_date": date_key})
        existing = []

    if len(existing) < 3:
        catalog_rows = await db.tv_dm_prayer_audio_catalog.find({"status": "active"}, {"_id": 0}).sort("catalog_index", 1).to_list(5000)
        if not catalog_rows:
            return {
                "status": "error",
                "published_date": date_key,
                "created_count": 0,
                "today_total": len(existing),
                "notifications": {"users_scanned": 0, "in_app_sent": 0, "email_sent": 0, "email_skipped": 0},
                "catalog_seed": seed_info,
                "error": "catalog_empty",
            }

        seed = _daily_audio_seed(date_key)
        to_create = 3 - len(existing)
        for i in range(to_create):
            slot = len(existing) + i + 1
            pick_index = (seed + i) % len(catalog_rows)
            source = catalog_rows[pick_index]
            doc = _build_daily_drop_doc_from_catalog(date_key, slot, source)
            await db.tv_dm_prayer_audio.update_one(
                {"audio_id": doc["audio_id"]},
                {"$set": doc, "$setOnInsert": {"created_at": _iso_now()}},
                upsert=True,
            )
            clean_doc = dict(doc)
            clean_doc.pop("_id", None)
            created_docs.append(clean_doc)

    todays_items = await db.tv_dm_prayer_audio.find({"published_date": date_key}, {"_id": 0}).sort("slot", 1).to_list(20)

    already_notified = await db.tv_dm_audio_daily_drop_runs.find_one(
        {"date_key": date_key},
        {"_id": 0, "notified": 1},
    )
    notification_stats = {"users_scanned": 0, "in_app_sent": 0, "email_sent": 0, "email_skipped": 0}
    if notify_users and (force or not already_notified or not bool(already_notified.get("notified", False))):
        notification_stats = await _dispatch_prayer_audio_drop_notifications(db, date_key, todays_items, max_users=max_users)
        await db.tv_dm_audio_daily_drop_runs.update_one(
            {"date_key": date_key},
            {
                "$set": {
                    "date_key": date_key,
                    "audio_ids": [it.get("audio_id") for it in todays_items[:3]],
                    "notified": True,
                    "notification_stats": notification_stats,
                    "updated_at": _iso_now(),
                },
                "$setOnInsert": {"created_at": _iso_now()},
            },
            upsert=True,
        )

    return {
        "status": "ok",
        "published_date": date_key,
        "created_count": len(created_docs),
        "today_total": len(todays_items),
        "notifications": notification_stats,
        "catalog_seed": seed_info,
        "catalog_total": int(await db.tv_dm_prayer_audio_catalog.count_documents({})),
    }


def _default_reminder_prefs(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "in_app_enabled": True,
        "email_enabled": False,
        "quiet_hours_start": 22,
        "quiet_hours_end": 6,
        "timezone": "UTC",
        "daily_gift_hour_utc": 7,
        "weekly_lookback_day": "sun",
    }


class MeditationCheckinRequest(BaseModel):
    user_id: str
    heart_text: str = Field(min_length=2, max_length=1600)
    mood: str = Field(default="calm", max_length=64)
    energy: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    request_support: bool = False


class MeditationJournalRequest(BaseModel):
    user_id: str
    title: str = Field(default="Reflection", max_length=160)
    content: str = Field(min_length=2, max_length=5000)
    prayer_text: str = Field(default="", max_length=5000)
    visibility: Literal["private", "community"] = "private"


class MeditationCompanionRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=2, max_length=2400)
    session_id: Optional[str] = None
    language: str = Field(default="en", max_length=16)


class MeditationSomaticCompleteRequest(BaseModel):
    user_id: str
    invitation_id: str
    duration_sec: int = Field(default=120, ge=30, le=1800)
    felt_shift: str = Field(default="", max_length=200)


class MeditationCommunityShareRequest(BaseModel):
    user_id: str
    text: str = Field(min_length=3, max_length=2000)
    anonymized: bool = True
    tags: list[str] = Field(default_factory=list)


class MeditationPrayerSupportRequest(BaseModel):
    user_id: str
    post_id: str


class MeditationJourneyPlanRequest(BaseModel):
    user_id: str
    focus_area: str = Field(default="peace", max_length=120)
    timeframe_days: int = Field(default=7, ge=3, le=30)


class MeditationReminderPrefsRequest(BaseModel):
    user_id: str
    in_app_enabled: bool = True
    email_enabled: bool = False
    quiet_hours_start: int = Field(default=22, ge=0, le=23)
    quiet_hours_end: int = Field(default=6, ge=0, le=23)
    timezone: str = Field(default="UTC", max_length=64)
    daily_gift_hour_utc: int = Field(default=7, ge=0, le=23)
    weekly_lookback_day: str = Field(default="sun", max_length=12)


class MeditationReminderCreateRequest(BaseModel):
    user_id: str
    title: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=3, max_length=1500)
    channel: Literal["in_app", "email", "both"] = "in_app"
    scheduled_for_iso: str
    kind: str = Field(default="nudge", max_length=80)


class MeditationNotifyNowRequest(BaseModel):
    user_id: str
    kind: str = Field(default="daily_gift", max_length=80)


class MeditationSafetyCheckRequest(BaseModel):
    user_id: str
    text: str = Field(min_length=2, max_length=2400)


class MeditationDigestRequest(BaseModel):
    user_id: str
    days: int = Field(default=7, ge=3, le=30)


class MeditationPrayerAudioPlayRequest(BaseModel):
    user_id: str
    audio_id: str


class MeditationPrayerAudioProgressRequest(BaseModel):
    user_id: str
    audio_id: str
    position_sec: int = Field(default=0, ge=0)
    duration_sec: int = Field(default=0, ge=0)
    completed: bool = False


class MeditationPrayerAudioFavoriteRequest(BaseModel):
    user_id: str
    audio_id: str
    favorite: bool = True


@router.get("/feature-map")
async def get_daily_meditation_feature_map(request: Request, user_id: Optional[str] = None):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    tiers = {"free": 0, "basic": 1, "premium": 2}
    current_tier = tiers.get(plan, 0)
    enriched = []
    for feat in MEDITATION_FEATURES:
        needed = tiers.get(str(feat.get("tier", "free")), 0)
        enriched.append({**feat, "available": current_tier >= needed})
    return {"tab": "Daily Meditation", "total_features": len(enriched), "features": enriched, "plan": plan}


@router.get("/health")
async def get_daily_meditation_health(request: Request):
    user = await require_auth(request)
    db = get_db()
    plan = await _get_user_plan(db, user.user_id)
    return {
        "ok": True,
        "service": "travel-visa-daily-meditation",
        "feature_number": 25,
        "feature_id": "daily-meditation",
        "feature_route": "/features/daily-meditation",
        "plan": plan,
        "scope_label": _scope_label(plan),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/overview/{user_id}")
async def get_daily_meditation_overview(user_id: str, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    limits = _limits_for(plan)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    usage_rows = await db.tv_dm_usage.find(
        {"user_id": scoped_user_id, "bucket": today, "window": "daily"},
        {"_id": 0, "action": 1, "count": 1},
    ).to_list(40)
    usage_today = {row.get("action"): int(row.get("count", 0)) for row in usage_rows}

    progress = await db.tv_dm_progress.find_one({"user_id": scoped_user_id}, {"_id": 0})
    if not progress:
        progress = {
            "user_id": scoped_user_id,
            "checkins_total": 0,
            "journal_entries_total": 0,
            "somatic_completed_total": 0,
            "community_posts_total": 0,
            "prayer_support_given": 0,
            "last_active_at": "",
        }

    pending_reminders = await db.tv_dm_reminders.count_documents({"user_id": scoped_user_id, "status": "pending", "enabled": True})
    unread = await db.tv_notifications.count_documents({"user_id": scoped_user_id, "module": "daily_meditation", "read": False})
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)
    today_audio_count = await db.tv_dm_prayer_audio.count_documents({"published_date": today_key})
    total_audio_library_count = await db.tv_dm_prayer_audio_catalog.count_documents({"status": "active"})
    available_audio_categories = len(PRAYER_AUDIO_CATEGORIES) if plan in {"basic", "premium"} else len(_free_audio_categories())

    return {
        "user_id": scoped_user_id,
        "plan": plan,
        "limits": limits,
        "usage_today": usage_today,
        "progress": progress,
        "pending_reminders": int(pending_reminders),
        "unread_notifications": int(unread),
        "today_prayer_audio_count": int(today_audio_count),
        "total_prayer_audio_count": int(total_audio_library_count),
        "available_prayer_audio_categories": int(available_audio_categories),
        "value_message": "Calm, relational, and spacious practice — presence over pressure.",
    }


@router.get("/daily-gift/{user_id}")
async def get_daily_gift(user_id: str, request: Request):
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    idx = datetime.now(timezone.utc).timetuple().tm_yday % len(DAILY_GIFTS)
    gift = DAILY_GIFTS[idx]
    return {
        "user_id": scoped_user_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "gift": gift,
        "estimated_minutes": 2,
    }


@router.get("/prayer-audio/categories")
async def prayer_audio_categories(request: Request):
    await require_auth(request)
    db = get_db()
    await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)
    total_audio_count = await db.tv_dm_prayer_audio_catalog.count_documents({"status": "active"})
    return {
        "total": len(PRAYER_AUDIO_CATEGORIES),
        "categories": PRAYER_AUDIO_CATEGORIES,
        "daily_drop_size": 3,
        "total_audio_count": int(total_audio_count),
        "target_audio_count": PRAYER_AUDIO_LIBRARY_TARGET,
    }


@router.post("/prayer-audio/publish/run-now")
async def prayer_audio_publish_run_now(request: Request, force: bool = Body(default=False, embed=True)):
    await require_admin(request)
    result = await run_daily_prayer_audio_auto_publish(force=force, max_users=700, notify_users=True)
    return result


@router.post("/prayer-audio/catalog/seed/run-now")
async def prayer_audio_catalog_seed_run_now(request: Request, target_count: int = Body(default=PRAYER_AUDIO_LIBRARY_TARGET, embed=True)):
    await require_admin(request)
    db = get_db()
    if target_count < PRAYER_AUDIO_LIBRARY_TARGET:
        target_count = PRAYER_AUDIO_LIBRARY_TARGET
    result = await _ensure_prayer_audio_catalog_seeded(db, target_count)
    return {
        "status": "ok",
        "target_count": int(target_count),
        "seed": result,
        "catalog_total": int(await db.tv_dm_prayer_audio_catalog.count_documents({})),
    }


@router.get("/prayer-audio/catalog/stats")
async def prayer_audio_catalog_stats(request: Request):
    await require_auth(request)
    db = get_db()
    await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)
    total_audio_count = await db.tv_dm_prayer_audio_catalog.count_documents({"status": "active"})
    return {
        "category_total": len(PRAYER_AUDIO_CATEGORIES),
        "audio_total": int(total_audio_count),
        "target_audio_total": PRAYER_AUDIO_LIBRARY_TARGET,
        "daily_drop_size": 3,
    }


@router.get("/prayer-audio/today/{user_id}")
async def prayer_audio_today(user_id: str, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    await run_daily_prayer_audio_auto_publish(force=False, max_users=0, notify_users=False)
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items = await db.tv_dm_prayer_audio.find({"published_date": date_key}, {"_id": 0}).sort("slot", 1).to_list(10)

    enriched = []
    for row in items[:3]:
        category = str(row.get("category") or "")
        allowed = _audio_category_allowed(plan, category)
        enriched.append({
            **row,
            "locked": not allowed,
            "available": allowed,
        })

    if enriched:
        await _record_audio_funnel_event(
            db,
            user_id=scoped_user_id,
            event_type="drop_opened",
            plan=plan,
            metadata={
                "published_date": date_key,
                "audio_ids": [str(it.get("audio_id") or "") for it in enriched[:3]],
                "categories": [str(it.get("category") or "") for it in enriched[:3]],
                "touch": "daily_drop",
            },
            dedupe_scope=f"{scoped_user_id}:drop_opened:{date_key}",
        )

    return {
        "published_date": date_key,
        "plan": plan,
        "items": enriched,
        "free_access_categories": sorted(list(_free_audio_categories())),
    }


@router.get("/prayer-audio/library/{user_id}")
async def prayer_audio_library(
    user_id: str,
    request: Request,
    page: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=60, ge=3, le=300),
):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)
    skip = (page - 1) * limit
    total = await db.tv_dm_prayer_audio_catalog.count_documents({"status": "active"})
    rows = await db.tv_dm_prayer_audio_catalog.find(
        {"status": "active"},
        {"_id": 0},
    ).sort("catalog_index", 1).skip(skip).limit(limit).to_list(limit)
    items = []
    for row in rows:
        category = str(row.get("category") or "")
        allowed = _audio_category_allowed(plan, category)
        items.append({**row, "locked": not allowed, "available": allowed})
    return {"plan": plan, "total": int(total), "page": page, "limit": limit, "items": items}


@router.get("/prayer-audio/semantic-search/{user_id}")
async def prayer_audio_semantic_search(
    user_id: str,
    request: Request,
    q: str = Query(default="", max_length=200),
    intent: str = Query(default="", max_length=80),
    scripture: str = Query(default="", max_length=120),
    mood: str = Query(default="", max_length=80),
    category: str = Query(default="", max_length=140),
    limit: int = Query(default=20, ge=3, le=60),
):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)

    q_norm = str(q or "").strip().lower()
    intent_norm = str(intent or "").strip().lower()
    scripture_norm = str(scripture or "").strip().lower()
    mood_norm = str(mood or "").strip().lower()
    category_norm = str(category or "").strip().lower()

    if not any([q_norm, intent_norm, scripture_norm, mood_norm, category_norm]):
        raise HTTPException(status_code=400, detail="Provide at least one search signal: q, intent, scripture, mood, or category")

    query_tokens = _tokenize_lower(q_norm)
    scripture_tokens = _tokenize_lower(scripture_norm)

    intent_tokens: list[str] = []
    if intent_norm:
        intent_tokens.extend(_tokenize_lower(intent_norm))
        intent_tokens.extend(PRAYER_INTENT_SIGNALS.get(intent_norm, []))

    mood_intents = PRAYER_MOOD_SIGNALS.get(mood_norm, [])
    for mood_intent in mood_intents:
        intent_tokens.extend(PRAYER_INTENT_SIGNALS.get(mood_intent, []))
        intent_tokens.append(mood_intent)

    intent_tokens = list(dict.fromkeys([token for token in intent_tokens if token]))

    base_query = {"status": "active"}
    if category_norm:
        base_query["category"] = {"$regex": re.escape(category_norm), "$options": "i"}

    rows = await db.tv_dm_prayer_audio_catalog.find(base_query, {"_id": 0}).limit(1200).to_list(1200)
    scored = []

    for row in rows:
        score, reasons = _semantic_search_score(
            row,
            query_tokens=query_tokens,
            scripture_tokens=scripture_tokens,
            intent_tokens=intent_tokens,
        )

        category_val = str(row.get("category") or "")
        if mood_norm and mood_intents and not any(signal in category_val.lower() for signal in mood_intents):
            # Keep mood as soft signal if explicit query/scripture intent exists
            if not (query_tokens or scripture_tokens):
                score -= 2

        if score <= 0:
            continue

        allowed = _audio_category_allowed(plan, category_val)
        scored.append({
            **row,
            "locked": not allowed,
            "available": allowed,
            "semantic_score": score,
            "match_reasons": reasons,
        })

    scored.sort(key=lambda x: (int(x.get("semantic_score", 0)), -int(x.get("catalog_index", 0))), reverse=True)
    items = scored[:limit]

    return {
        "plan": plan,
        "filters": {
            "q": q_norm,
            "intent": intent_norm,
            "scripture": scripture_norm,
            "mood": mood_norm,
            "category": category_norm,
        },
        "signals": {
            "intent_keywords": intent_tokens[:20],
            "mood_intent_bridge": mood_intents,
        },
        "total_matches": len(scored),
        "items": items,
    }


@router.post("/prayer-audio/play")
async def prayer_audio_play(req: MeditationPrayerAudioPlayRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    row = await db.tv_dm_prayer_audio.find_one({"audio_id": req.audio_id}, {"_id": 0})
    source_scope = "daily_drop"
    if not row:
        row = await db.tv_dm_prayer_audio_catalog.find_one({"audio_id": req.audio_id, "status": "active"}, {"_id": 0})
        source_scope = "catalog"
    if not row:
        raise HTTPException(status_code=404, detail="Prayer audio not found")

    if not _audio_category_allowed(plan, str(row.get("category") or "")):
        raise HTTPException(status_code=403, detail="Upgrade plan to unlock this prayer audio category")

    quota = await _check_limit(db, scoped_user_id, plan, "dm_audio_play", "daily_audio_plays", "daily")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Daily prayer audio listen limit reached for {plan} plan")

    await db.tv_dm_prayer_audio_playback.update_one(
        {"user_id": scoped_user_id, "audio_id": req.audio_id},
        {
            "$inc": {"plays": 1},
            "$set": {
                "user_id": scoped_user_id,
                "audio_id": req.audio_id,
                "category": row.get("category"),
                "last_played_at": _iso_now(),
                "updated_at": _iso_now(),
            },
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )
    await _record_audio_funnel_event(
        db,
        user_id=scoped_user_id,
        event_type="played",
        plan=plan,
        audio_id=req.audio_id,
        metadata={
            "category": row.get("category"),
            "from": "prayer_audio_player",
            "source_scope": source_scope,
        },
        dedupe_scope=f"{scoped_user_id}:played:{req.audio_id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
    )
    return {"status": "ok", "plan": plan, "quota": quota, "audio": row}


@router.post("/prayer-audio/progress")
async def prayer_audio_progress(req: MeditationPrayerAudioProgressRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    progress_pct = 0.0
    if req.duration_sec > 0:
        progress_pct = round(min(100.0, (req.position_sec / req.duration_sec) * 100), 2)
    await db.tv_dm_prayer_audio_progress.update_one(
        {"user_id": scoped_user_id, "audio_id": req.audio_id},
        {
            "$set": {
                "user_id": scoped_user_id,
                "audio_id": req.audio_id,
                "position_sec": req.position_sec,
                "duration_sec": req.duration_sec,
                "progress_pct": progress_pct,
                "completed": bool(req.completed),
                "updated_at": _iso_now(),
            },
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )

    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if req.position_sec >= 30:
        await _record_audio_funnel_event(
            db,
            user_id=scoped_user_id,
            event_type="played_30s",
            plan=plan,
            audio_id=req.audio_id,
            metadata={"position_sec": req.position_sec, "duration_sec": req.duration_sec, "progress_pct": progress_pct},
            dedupe_scope=f"{scoped_user_id}:played_30s:{req.audio_id}:{date_key}",
        )
    if progress_pct >= 75:
        await _record_audio_funnel_event(
            db,
            user_id=scoped_user_id,
            event_type="played_75pct",
            plan=plan,
            audio_id=req.audio_id,
            metadata={"position_sec": req.position_sec, "duration_sec": req.duration_sec, "progress_pct": progress_pct},
            dedupe_scope=f"{scoped_user_id}:played_75pct:{req.audio_id}:{date_key}",
        )
    if bool(req.completed) or progress_pct >= 95:
        await _record_audio_funnel_event(
            db,
            user_id=scoped_user_id,
            event_type="completed",
            plan=plan,
            audio_id=req.audio_id,
            metadata={"position_sec": req.position_sec, "duration_sec": req.duration_sec, "progress_pct": progress_pct},
            dedupe_scope=f"{scoped_user_id}:completed:{req.audio_id}:{date_key}",
        )

    return {"status": "saved", "progress_pct": progress_pct}


@router.get("/prayer-audio/progress/{user_id}")
async def prayer_audio_progress_list(user_id: str, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    rows = await db.tv_dm_prayer_audio_progress.find({"user_id": scoped_user_id}, {"_id": 0}).sort("updated_at", -1).limit(120).to_list(120)
    return {"items": rows, "total": len(rows)}


@router.post("/prayer-audio/favorite")
async def prayer_audio_favorite(req: MeditationPrayerAudioFavoriteRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    if req.favorite:
        await db.tv_dm_prayer_audio_favorites.update_one(
            {"user_id": scoped_user_id, "audio_id": req.audio_id},
            {
                "$set": {"user_id": scoped_user_id, "audio_id": req.audio_id, "updated_at": _iso_now()},
                "$setOnInsert": {"created_at": _iso_now()},
            },
            upsert=True,
        )
    else:
        await db.tv_dm_prayer_audio_favorites.delete_one({"user_id": scoped_user_id, "audio_id": req.audio_id})
    return {"status": "ok", "favorite": req.favorite}


@router.get("/prayer-audio/favorites/{user_id}")
async def prayer_audio_favorites(user_id: str, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    favs = await db.tv_dm_prayer_audio_favorites.find({"user_id": scoped_user_id}, {"_id": 0, "audio_id": 1}).to_list(300)
    ids = [str(x.get("audio_id")) for x in favs if x.get("audio_id")]
    if not ids:
        return {"items": [], "total": 0}

    catalog_rows = await db.tv_dm_prayer_audio_catalog.find({"audio_id": {"$in": ids}, "status": "active"}, {"_id": 0}).to_list(500)
    found_ids = {str(r.get("audio_id") or "") for r in catalog_rows}
    remaining_ids = [x for x in ids if x not in found_ids]
    daily_rows = []
    if remaining_ids:
        daily_rows = await db.tv_dm_prayer_audio.find({"audio_id": {"$in": remaining_ids}}, {"_id": 0}).to_list(500)

    rows = catalog_rows + daily_rows
    rows.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return {"items": rows, "total": len(rows)}


@router.get("/prayer-audio/recommendations/{user_id}")
async def prayer_audio_recommendations(user_id: str, request: Request, limit: int = Query(default=6, ge=3, le=30)):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    await _ensure_prayer_audio_catalog_seeded(db, PRAYER_AUDIO_LIBRARY_TARGET)
    recent = await db.tv_dm_checkins.find({"user_id": scoped_user_id}, {"_id": 0, "mood": 1}).sort("created_at", -1).limit(8).to_list(8)
    mood_map = {
        "anxious": "Peace & Stillness",
        "overwhelmed": "Strength in Trials",
        "tired": "Sleep & Rest",
        "grateful": "Thanksgiving & Testimony",
        "hopeful": "Hope in Waiting",
    }
    target = []
    for row in recent:
        mood = str(row.get("mood") or "").strip().lower()
        if mood in mood_map:
            target.append(mood_map[mood])
    if not target:
        target = ["Morning Gratitude", "Peace & Stillness", "Guidance & Discernment"]

    rows = await db.tv_dm_prayer_audio_catalog.find(
        {"category": {"$in": target}, "status": "active"},
        {"_id": 0},
    ).sort("catalog_index", 1).limit(limit).to_list(limit)
    out = []
    for row in rows:
        category = str(row.get("category") or "")
        allowed = _audio_category_allowed(plan, category)
        out.append({**row, "locked": not allowed, "available": allowed})
    return {"target_categories": target, "items": out, "total": len(out)}


@router.get("/admin/prayer-audio/funnel-summary")
async def admin_prayer_audio_funnel_summary(
    request: Request,
    days: int = Query(default=14, ge=7, le=90),
    conversion_window_days: int = Query(default=14, ge=3, le=60),
):
    await require_admin(request)
    db = get_db()
    result = await _build_prayer_audio_funnel_analytics(db, days=days, conversion_window_days=conversion_window_days)
    return result


@router.get("/admin/prayer-audio/funnel-export")
async def admin_prayer_audio_funnel_export(
    request: Request,
    days: int = Query(default=14, ge=7, le=90),
    conversion_window_days: int = Query(default=14, ge=3, le=60),
    format: Literal["json", "csv"] = Query(default="csv"),
):
    await require_admin(request)
    db = get_db()
    report = await _build_prayer_audio_funnel_analytics(db, days=days, conversion_window_days=conversion_window_days)
    if format == "json":
        return report

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "cohort_plan",
        "drop_opened",
        "played",
        "played_30s",
        "played_75pct",
        "completed",
        "upgraded",
        "play_rate_pct",
        "played_30s_rate_pct",
        "played_75pct_rate_pct",
        "completion_rate_pct",
        "upgrade_rate_pct",
    ])

    for plan in ["free", "basic", "premium"]:
        bucket = report.get("cohorts", {}).get(plan, {})
        writer.writerow([
            plan,
            int(bucket.get("drop_opened", 0)),
            int(bucket.get("played", 0)),
            int(bucket.get("played_30s", 0)),
            int(bucket.get("played_75pct", 0)),
            int(bucket.get("completed", 0)),
            int(bucket.get("upgraded", 0)),
            float(bucket.get("play_rate_pct", 0.0)),
            float(bucket.get("played_30s_rate_pct", 0.0)),
            float(bucket.get("played_75pct_rate_pct", 0.0)),
            float(bucket.get("completion_rate_pct", 0.0)),
            float(bucket.get("upgrade_rate_pct", 0.0)),
        ])

    totals = report.get("totals", {})
    writer.writerow([
        "all",
        int(totals.get("drop_opened", 0)),
        int(totals.get("played", 0)),
        int(totals.get("played_30s", 0)),
        int(totals.get("played_75pct", 0)),
        int(totals.get("completed", 0)),
        int(totals.get("upgraded", 0)),
        float(totals.get("play_rate_pct", 0.0)),
        float(totals.get("played_30s_rate_pct", 0.0)),
        float(totals.get("played_75pct_rate_pct", 0.0)),
        float(totals.get("completion_rate_pct", 0.0)),
        float(totals.get("upgrade_rate_pct", 0.0)),
    ])

    output.seek(0)
    filename = f"daily_meditation_prayer_audio_funnel_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/admin/prayer-audio/upgrade-attribution/categories")
async def admin_prayer_audio_upgrade_attribution_categories(
    request: Request,
    days: int = Query(default=30, ge=14, le=180),
    conversion_window_days: int = Query(default=14, ge=3, le=60),
    top: int = Query(default=20, ge=5, le=80),
):
    await require_admin(request)
    db = get_db()
    report = await _build_prayer_audio_upgrade_attribution_by_category(
        db,
        days=days,
        conversion_window_days=conversion_window_days,
        top=top,
    )
    return report


@router.get("/admin/prayer-audio/upgrade-attribution/export")
async def admin_prayer_audio_upgrade_attribution_export(
    request: Request,
    days: int = Query(default=30, ge=14, le=180),
    conversion_window_days: int = Query(default=14, ge=3, le=60),
    top: int = Query(default=20, ge=5, le=80),
    format: Literal["json", "csv"] = Query(default="csv"),
):
    await require_admin(request)
    db = get_db()
    report = await _build_prayer_audio_upgrade_attribution_by_category(
        db,
        days=days,
        conversion_window_days=conversion_window_days,
        top=top,
    )
    if format == "json":
        return report

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "category",
        "touch_users",
        "upgraded_users",
        "upgrades_to_basic",
        "upgrades_to_premium",
        "source_free",
        "source_basic",
        "source_premium",
        "upgrade_rate_pct",
    ])
    for row in report.get("category_slices", []):
        writer.writerow([
            str(row.get("category") or ""),
            int(row.get("touch_users", 0)),
            int(row.get("upgraded_users", 0)),
            int(row.get("upgrades_to_basic", 0)),
            int(row.get("upgrades_to_premium", 0)),
            int(row.get("source_free", 0)),
            int(row.get("source_basic", 0)),
            int(row.get("source_premium", 0)),
            float(row.get("upgrade_rate_pct", 0.0)),
        ])

    totals = report.get("totals", {})
    writer.writerow([
        "ALL",
        int(totals.get("distinct_touch_users", 0)),
        int(totals.get("distinct_upgraded_users", 0)),
        "",
        "",
        "",
        "",
        "",
        "",
    ])

    output.seek(0)
    filename = f"daily_meditation_prayer_audio_upgrade_attribution_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/checkin")
async def create_meditation_checkin(req: MeditationCheckinRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    quota = await _check_limit(db, scoped_user_id, plan, "dm_checkins", "daily_checkins", "daily")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Daily check-in limit reached for {plan} plan")

    checkin = {
        "checkin_id": f"dmc_{uuid.uuid4().hex[:12]}",
        "user_id": scoped_user_id,
        "heart_text": req.heart_text.strip(),
        "mood": req.mood.strip().lower()[:64],
        "energy": int(req.energy),
        "tags": [str(t).strip().lower()[:40] for t in req.tags if str(t).strip()][:12],
        "request_support": bool(req.request_support),
        "created_at": _iso_now(),
    }
    await db.tv_dm_checkins.insert_one(checkin)
    checkin.pop("_id", None)

    await db.tv_dm_progress.update_one(
        {"user_id": scoped_user_id},
        {
            "$inc": {"checkins_total": 1},
            "$set": {"last_active_at": _iso_now(), "updated_at": _iso_now()},
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )

    await _create_in_app_notification(
        db,
        scoped_user_id,
        "Check-in saved",
        "Your reflection was safely saved. You can revisit it in Look Back anytime.",
        "checkin_saved",
        {"checkin_id": checkin["checkin_id"]},
    )

    mood_text = checkin.get("mood", "")
    if req.request_support or mood_text in {"anxious", "overwhelmed", "burnout", "hopeless"}:
        await _create_in_app_notification(
            db,
            scoped_user_id,
            "Support available",
            "You are not alone. If you feel unsafe, please contact local emergency or crisis support immediately.",
            "safety_support",
            {"severity": "elevated"},
        )

    return {"status": "saved", "plan": plan, "quota": quota, "checkin": checkin}


@router.get("/checkins/{user_id}")
async def list_meditation_checkins(user_id: str, request: Request, limit: int = Query(default=30, ge=1, le=200)):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    rows = await db.tv_dm_checkins.find({"user_id": scoped_user_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"checkins": rows, "total": len(rows)}


@router.post("/journal")
async def create_journal_entry(req: MeditationJournalRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    quota = await _check_limit(db, scoped_user_id, plan, "dm_journal_entries", "daily_journal_entries", "daily")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Daily journal limit reached for {plan} plan")

    entry = {
        "entry_id": f"dmj_{uuid.uuid4().hex[:12]}",
        "user_id": scoped_user_id,
        "title": req.title.strip()[:160],
        "content": req.content.strip(),
        "prayer_text": req.prayer_text.strip(),
        "visibility": req.visibility,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    await db.tv_dm_journal.insert_one(entry)
    entry.pop("_id", None)

    await db.tv_dm_progress.update_one(
        {"user_id": scoped_user_id},
        {
            "$inc": {"journal_entries_total": 1},
            "$set": {"last_active_at": _iso_now(), "updated_at": _iso_now()},
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )

    return {"status": "saved", "entry": entry, "quota": quota, "plan": plan}


@router.get("/journal/{user_id}")
async def list_journal_entries(
    user_id: str,
    request: Request,
    limit: int = Query(default=30, ge=1, le=200),
    visibility: Optional[Literal["private", "community"]] = None,
):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    query = {"user_id": scoped_user_id}
    if visibility:
        query["visibility"] = visibility
    rows = await db.tv_dm_journal.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"entries": rows, "total": len(rows)}


@router.get("/somatic/library")
async def get_somatic_library(request: Request):
    await require_auth(request)
    return {"invitations": SOMATIC_INVITATIONS, "total": len(SOMATIC_INVITATIONS)}


@router.post("/somatic/complete")
async def complete_somatic_invitation(req: MeditationSomaticCompleteRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    quota = await _check_limit(db, scoped_user_id, plan, "dm_somatic_sessions", "daily_somatic_sessions", "daily")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Somatic session daily limit reached for {plan} plan")

    record = {
        "session_id": f"dms_{uuid.uuid4().hex[:12]}",
        "user_id": scoped_user_id,
        "invitation_id": req.invitation_id,
        "duration_sec": req.duration_sec,
        "felt_shift": req.felt_shift.strip()[:200],
        "completed_at": _iso_now(),
    }
    await db.tv_dm_somatic_sessions.insert_one(record)
    record.pop("_id", None)

    await db.tv_dm_progress.update_one(
        {"user_id": scoped_user_id},
        {
            "$inc": {"somatic_completed_total": 1},
            "$set": {"last_active_at": _iso_now(), "updated_at": _iso_now()},
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )
    return {"status": "completed", "session": record, "quota": quota, "plan": plan}


@router.get("/community/feed/{user_id}")
async def get_community_feed(user_id: str, request: Request, limit: int = Query(default=25, ge=1, le=100)):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    rows = await db.tv_dm_community_posts.find({"status": {"$ne": "removed"}}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for row in rows:
        supporters = set(row.get("prayer_support_user_ids") or [])
        row["prayed_by_me"] = scoped_user_id in supporters
        row.pop("prayer_support_user_ids", None)
    return {"posts": rows, "total": len(rows)}


@router.post("/community/share")
async def share_community_reflection(req: MeditationCommunityShareRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    if plan == "free":
        raise HTTPException(status_code=403, detail="Community posting is available on Basic or Premium plans")

    quota = await _check_limit(db, scoped_user_id, plan, "dm_community_posts", "weekly_community_posts", "weekly")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Weekly community posting limit reached for {plan} plan")

    post = {
        "post_id": f"dmp_{uuid.uuid4().hex[:12]}",
        "user_id": scoped_user_id,
        "text": req.text.strip(),
        "anonymized": req.anonymized,
        "display_name": "Anonymous" if req.anonymized else "Member",
        "tags": [str(t).strip().lower()[:40] for t in req.tags if str(t).strip()][:12],
        "prayer_support_count": 0,
        "prayer_support_user_ids": [],
        "status": "active",
        "created_at": _iso_now(),
    }
    await db.tv_dm_community_posts.insert_one(post)
    post.pop("_id", None)

    await db.tv_dm_progress.update_one(
        {"user_id": scoped_user_id},
        {
            "$inc": {"community_posts_total": 1},
            "$set": {"last_active_at": _iso_now(), "updated_at": _iso_now()},
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )
    return {"status": "shared", "post": {k: v for k, v in post.items() if k != "prayer_support_user_ids"}, "quota": quota}


@router.post("/community/pray")
async def support_with_prayer(req: MeditationPrayerSupportRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    post = await db.tv_dm_community_posts.find_one({"post_id": req.post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Community post not found")

    await db.tv_dm_community_posts.update_one(
        {"post_id": req.post_id},
        {
            "$addToSet": {"prayer_support_user_ids": scoped_user_id},
            "$set": {"updated_at": _iso_now()},
        },
    )

    updated = await db.tv_dm_community_posts.find_one({"post_id": req.post_id}, {"_id": 0, "prayer_support_user_ids": 1})
    support_ids = updated.get("prayer_support_user_ids", []) if updated else []
    count = len(support_ids)

    await db.tv_dm_community_posts.update_one({"post_id": req.post_id}, {"$set": {"prayer_support_count": count}})
    await db.tv_dm_progress.update_one(
        {"user_id": scoped_user_id},
        {
            "$inc": {"prayer_support_given": 1},
            "$set": {"last_active_at": _iso_now(), "updated_at": _iso_now()},
            "$setOnInsert": {"created_at": _iso_now()},
        },
        upsert=True,
    )

    owner_id = str(post.get("user_id") or "")
    if owner_id and owner_id != scoped_user_id:
        await _create_in_app_notification(
            db,
            owner_id,
            "Someone prayed for your reflection",
            "Your community reflection received prayer support.",
            "community_prayer_support",
            {"post_id": req.post_id},
        )

    return {"status": "supported", "post_id": req.post_id, "prayer_support_count": count}


@router.get("/lookback/{user_id}")
async def get_lookback(user_id: str, request: Request, days: int = Query(default=7, ge=3, le=90), include_ai_summary: bool = True):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    checkins = await db.tv_dm_checkins.find({"user_id": scoped_user_id, "created_at": {"$gte": since}}, {"_id": 0}).to_list(500)
    journal = await db.tv_dm_journal.find({"user_id": scoped_user_id, "created_at": {"$gte": since}}, {"_id": 0}).to_list(500)
    somatic = await db.tv_dm_somatic_sessions.find({"user_id": scoped_user_id, "completed_at": {"$gte": since}}, {"_id": 0}).to_list(500)

    mood_counts = {}
    tag_counts = {}
    for c in checkins:
        mood = str(c.get("mood") or "unknown")
        mood_counts[mood] = mood_counts.get(mood, 0) + 1
        for tag in c.get("tags") or []:
            t = str(tag).strip().lower()
            if not t:
                continue
            tag_counts[t] = tag_counts.get(t, 0) + 1

    highlights = []
    for doc in (checkins[:5] + journal[:5]):
        text = str(doc.get("heart_text") or doc.get("content") or "").strip()
        if text:
            highlights.append(text[:220])

    summary = (
        f"In the last {days} days: {len(checkins)} check-ins, {len(journal)} journal entries, "
        f"and {len(somatic)} somatic practices."
    )

    ai_summary = ""
    if include_ai_summary:
        plan = await _get_user_plan(db, scoped_user_id)
        if plan in {"basic", "premium"}:
            quota = await _check_limit(db, scoped_user_id, plan, "dm_ai_insights", "daily_ai_insights", "daily")
            if quota["allowed"] and LLM_KEY:
                try:
                    prompt = {
                        "days": days,
                        "mood_counts": mood_counts,
                        "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:6],
                        "highlights": highlights[:5],
                    }
                    chat = LlmChat(
                        api_key=LLM_KEY,
                        session_id=f"dm-lookback-{scoped_user_id}-{uuid.uuid4().hex[:8]}",
                        system_message=(
                            "You are a compassionate Daily Meditation insights guide."
                            "Be warm, concise, faith-sensitive, and non-judgmental."
                            "Do not provide medical diagnosis."
                        ),
                    ).with_model("openai", "gpt-5.2")
                    ai_summary = await chat.send_message(
                        UserMessage(
                            text=(
                                "Create a 4-6 sentence weekly reflection summary with:\n"
                                "1) one observed pattern\n"
                                "2) one gentle encouragement\n"
                                "3) one next small practice step\n"
                                f"Data: {json.dumps(prompt)}"
                            )
                        )
                    )
                except Exception:
                    ai_summary = "Your recent rhythm shows consistency. Keep one gentle practice each day and return with honesty."

    return {
        "days": days,
        "summary": summary,
        "mood_counts": mood_counts,
        "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:8],
        "highlights": highlights[:10],
        "counts": {
            "checkins": len(checkins),
            "journal_entries": len(journal),
            "somatic_sessions": len(somatic),
        },
        "ai_summary": ai_summary,
    }


@router.post("/companion/chat")
async def companion_chat(req: MeditationCompanionRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    quota = await _check_limit(db, scoped_user_id, plan, "dm_ai_companion", "daily_ai_companion", "daily")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Daily companion limit reached for {plan} plan")

    if not LLM_KEY:
        raise HTTPException(status_code=503, detail="EMERGENT_LLM_KEY is not configured")

    session_id = req.session_id or f"dm-session-{uuid.uuid4().hex[:10]}"
    now_iso = _iso_now()

    history = await db.tv_dm_companion_messages.find(
        {"user_id": scoped_user_id, "session_id": session_id},
        {"_id": 0, "role": 1, "content": 1},
    ).sort("created_at", -1).limit(8).to_list(8)
    history.reverse()

    transcript = "\n".join([f"{msg.get('role','user')}: {msg.get('content','')}" for msg in history])
    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=session_id,
        system_message=(
            "You are a gentle Daily Meditation companion rooted in Christian faith language. "
            "Be calm, relational, and spacious—not performative. "
            "Support emotional reflection and embodied peace practices. "
            "Do not claim to replace medical or mental-health care."
        ),
    ).with_model("openai", "gpt-5.2")

    user_payload = (
        f"Language: {req.language}\n"
        f"Recent context:\n{transcript or 'No previous context'}\n\n"
        f"User message: {req.message.strip()}\n\n"
        "Respond with: (1) warm reflection, (2) one scripture-aligned encouragement, "
        "(3) one 60-120 second practical somatic step."
    )

    try:
        response_text = await chat.send_message(UserMessage(text=user_payload))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Companion response error: {str(exc)}")

    await db.tv_dm_companion_messages.insert_many(
        [
            {
                "message_id": f"dmm_{uuid.uuid4().hex[:12]}",
                "user_id": scoped_user_id,
                "session_id": session_id,
                "role": "user",
                "content": req.message.strip(),
                "created_at": now_iso,
            },
            {
                "message_id": f"dmm_{uuid.uuid4().hex[:12]}",
                "user_id": scoped_user_id,
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "created_at": _iso_now(),
            },
        ]
    )

    return {"session_id": session_id, "response": response_text, "quota": quota}


@router.get("/companion/history/{user_id}")
async def companion_history(user_id: str, request: Request, session_id: Optional[str] = None):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    query = {"user_id": scoped_user_id}
    if session_id:
        query["session_id"] = session_id
    rows = await db.tv_dm_companion_messages.find(query, {"_id": 0}).sort("created_at", 1).limit(400).to_list(400)
    return {"messages": rows, "total": len(rows)}


@router.post("/journey-plan")
async def generate_journey_plan(req: MeditationJourneyPlanRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    quota = await _check_limit(db, scoped_user_id, plan, "dm_ai_journey_plans", "daily_ai_insights", "daily")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Daily journey plan limit reached for {plan} plan")

    if not LLM_KEY:
        raise HTTPException(status_code=503, detail="EMERGENT_LLM_KEY is not configured")

    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"dm-plan-{scoped_user_id}-{uuid.uuid4().hex[:8]}",
        system_message=(
            "You design calm, practical daily meditation plans rooted in scripture reflection, "
            "gentle journaling, and embodied peace practices."
        ),
    ).with_model("openai", "gpt-5.2")

    prompt = (
        "Return strict JSON with this shape: "
        "{\"focus_area\":str,\"timeframe_days\":int,\"days\":[{\"day\":int,\"theme\":str,\"scripture\":str,\"practice\":str,\"journal_prompt\":str}]}\n"
        f"Focus area: {req.focus_area}; timeframe_days: {req.timeframe_days}."
    )

    result = await chat.send_message(UserMessage(text=prompt))
    try:
        parsed = json.loads(result.strip().strip("```json").strip("```"))
    except Exception:
        parsed = {
            "focus_area": req.focus_area,
            "timeframe_days": req.timeframe_days,
            "days": [
                {
                    "day": 1,
                    "theme": "Arrive honestly",
                    "scripture": "Psalm 46:10",
                    "practice": "2-minute slow breathing",
                    "journal_prompt": "What do I need to release today?",
                }
            ],
        }

    plan_doc = {
        "plan_id": f"dmp_{uuid.uuid4().hex[:12]}",
        "user_id": scoped_user_id,
        "focus_area": req.focus_area,
        "timeframe_days": req.timeframe_days,
        "plan": parsed,
        "created_at": _iso_now(),
    }
    await db.tv_dm_journey_plans.insert_one(plan_doc)
    plan_doc.pop("_id", None)
    return {"status": "created", "journey_plan": plan_doc, "quota": quota}


@router.get("/progress/{user_id}")
async def meditation_progress(user_id: str, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    progress = await db.tv_dm_progress.find_one({"user_id": scoped_user_id}, {"_id": 0})
    if not progress:
        progress = {
            "user_id": scoped_user_id,
            "checkins_total": 0,
            "journal_entries_total": 0,
            "somatic_completed_total": 0,
            "community_posts_total": 0,
            "prayer_support_given": 0,
            "last_active_at": "",
        }

    milestones = [
        {"id": "first_checkin", "label": "First Check-In", "done": progress.get("checkins_total", 0) >= 1},
        {"id": "seven_checkins", "label": "7 Check-Ins", "done": progress.get("checkins_total", 0) >= 7},
        {"id": "ten_journals", "label": "10 Journal Entries", "done": progress.get("journal_entries_total", 0) >= 10},
        {"id": "three_somatic", "label": "3 Somatic Sessions", "done": progress.get("somatic_completed_total", 0) >= 3},
        {"id": "community_support", "label": "3 Prayer Supports Given", "done": progress.get("prayer_support_given", 0) >= 3},
    ]
    done_count = len([m for m in milestones if m["done"]])
    score = round((done_count / max(1, len(milestones))) * 100)

    next_step = "Complete one heart check-in today."
    if progress.get("checkins_total", 0) >= 1:
        next_step = "Add one private journal reflection."
    if progress.get("journal_entries_total", 0) >= 3:
        next_step = "Complete one somatic invitation for embodied calm."

    return {
        "progress": progress,
        "milestones": milestones,
        "progress_score": score,
        "next_step": next_step,
    }


@router.get("/reminders/prefs/{user_id}")
async def get_reminder_prefs(user_id: str, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    prefs = await db.tv_dm_reminder_prefs.find_one({"user_id": scoped_user_id}, {"_id": 0})
    if not prefs:
        prefs = _default_reminder_prefs(scoped_user_id)
    return {"preferences": prefs}


@router.post("/reminders/prefs")
async def update_reminder_prefs(req: MeditationReminderPrefsRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    payload = {
        "user_id": scoped_user_id,
        "in_app_enabled": req.in_app_enabled,
        "email_enabled": req.email_enabled,
        "quiet_hours_start": req.quiet_hours_start,
        "quiet_hours_end": req.quiet_hours_end,
        "timezone": req.timezone,
        "daily_gift_hour_utc": req.daily_gift_hour_utc,
        "weekly_lookback_day": req.weekly_lookback_day,
        "updated_at": _iso_now(),
    }
    await db.tv_dm_reminder_prefs.update_one(
        {"user_id": scoped_user_id},
        {"$set": payload, "$setOnInsert": {"created_at": _iso_now()}},
        upsert=True,
    )
    return {"status": "updated", "preferences": payload}


@router.post("/reminders/schedule")
async def schedule_reminder(req: MeditationReminderCreateRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    reminder_id = f"dmr_{uuid.uuid4().hex[:12]}"
    doc = {
        "reminder_id": reminder_id,
        "user_id": scoped_user_id,
        "title": req.title.strip(),
        "message": req.message.strip(),
        "channel": req.channel,
        "kind": req.kind,
        "scheduled_for_iso": req.scheduled_for_iso,
        "status": "pending",
        "enabled": True,
        "attempts": 0,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "plan_at_create": plan,
    }
    await db.tv_dm_reminders.insert_one(doc)
    doc.pop("_id", None)
    return {"status": "scheduled", "reminder": doc}


async def run_daily_meditation_reminder_dispatch(batch_limit: int = 200):
    db = get_db()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    pending = await db.tv_dm_reminders.find(
        {
            "status": "pending",
            "enabled": True,
            "scheduled_for_iso": {"$lte": now_iso},
        },
        {"_id": 0},
    ).sort("scheduled_for_iso", 1).limit(batch_limit).to_list(batch_limit)

    sent = 0
    skipped = 0
    failed = 0
    for reminder in pending:
        reminder_id = reminder.get("reminder_id")
        user_id = reminder.get("user_id")
        if not reminder_id or not user_id:
            failed += 1
            continue

        prefs = await db.tv_dm_reminder_prefs.find_one({"user_id": user_id}, {"_id": 0})
        if not prefs:
            prefs = _default_reminder_prefs(user_id)

        hour = datetime.now(timezone.utc).hour
        quiet_start = int(prefs.get("quiet_hours_start", 22))
        quiet_end = int(prefs.get("quiet_hours_end", 6))
        in_quiet = (hour >= quiet_start) or (hour < quiet_end)
        if in_quiet and reminder.get("kind") != "manual_test":
            next_run = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            await db.tv_dm_reminders.update_one(
                {"reminder_id": reminder_id},
                {"$set": {"scheduled_for_iso": next_run, "updated_at": _iso_now()}, "$inc": {"attempts": 1}},
            )
            skipped += 1
            continue

        channels_sent = []
        try:
            if reminder.get("channel") in {"in_app", "both"} and bool(prefs.get("in_app_enabled", True)):
                await _create_in_app_notification(
                    db,
                    user_id,
                    str(reminder.get("title") or "Daily Meditation Reminder"),
                    str(reminder.get("message") or "Take a gentle moment to check in."),
                    "reminder",
                    {"reminder_id": reminder_id, "kind": reminder.get("kind")},
                )
                channels_sent.append("in_app")

            if reminder.get("channel") in {"email", "both"} and bool(prefs.get("email_enabled", False)):
                reminder_message = str(reminder.get('message') or '').strip() or "Take a gentle moment to check in."
                email_status = await _send_dm_email(
                    db,
                    user_id,
                    str(reminder.get("title") or "Daily Meditation Reminder"),
                    reminder_message,
                    "daily_meditation_reminder",
                    template_payload={
                        "title": str(reminder.get("title") or "Daily Meditation Reminder"),
                        "message": reminder_message,
                    },
                )
                if str(email_status).startswith("sent") or email_status == "sent":
                    channels_sent.append("email")

            await db.tv_dm_reminders.update_one(
                {"reminder_id": reminder_id},
                {
                    "$set": {
                        "status": "sent" if channels_sent else "skipped",
                        "channels_sent": channels_sent,
                        "sent_at": _iso_now(),
                        "updated_at": _iso_now(),
                    },
                    "$inc": {"attempts": 1},
                },
            )
            if channels_sent:
                sent += 1
            else:
                skipped += 1
        except Exception:
            failed += 1
            await db.tv_dm_reminders.update_one(
                {"reminder_id": reminder_id},
                {
                    "$set": {"status": "failed", "updated_at": _iso_now()},
                    "$inc": {"attempts": 1},
                },
            )

    return {
        "status": "ok",
        "scanned": len(pending),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "ran_at": now_iso,
    }


@router.post("/reminders/dispatch/run")
async def run_reminder_dispatch_now(request: Request, batch_limit: int = Body(default=100, embed=True)):
    await require_admin(request)
    result = await run_daily_meditation_reminder_dispatch(batch_limit=batch_limit)
    return result


@router.post("/reminders/notify-now")
async def notify_now(req: MeditationNotifyNowRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    reminder = {
        "reminder_id": f"dmr_{uuid.uuid4().hex[:12]}",
        "user_id": scoped_user_id,
        "title": "Daily Meditation Progress Reminder",
        "message": "Take one calm minute to check in and continue your journey.",
        "channel": "both",
        "kind": "manual_test",
        "scheduled_for_iso": _iso_now(),
        "status": "pending",
        "enabled": True,
        "attempts": 0,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    await db.tv_dm_reminders.insert_one(reminder)
    reminder.pop("_id", None)
    dispatch = await run_daily_meditation_reminder_dispatch(batch_limit=20)
    return {"status": "queued_and_dispatched", "reminder": reminder, "dispatch": dispatch}


@router.post("/digest/preview")
async def digest_preview(req: MeditationDigestRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    digest = await _build_weekly_digest_payload(db, scoped_user_id, req.days)
    return {"status": "ok", "digest": digest}


@router.post("/digest/send-now")
async def digest_send_now(req: MeditationDigestRequest, request: Request):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, req.user_id)
    digest = await _build_weekly_digest_payload(db, scoped_user_id, req.days)
    email_status = await _send_dm_email(
        db,
        scoped_user_id,
        digest["subject"],
        digest["html"],
        "daily_meditation_weekly_digest",
        template_payload={
            "days": int(digest.get("days") or req.days or 7),
            "dominant_theme": str((digest.get("stats") or {}).get("dominant_theme") or "steady"),
            "headline": str(digest.get("headline") or ""),
            "encouragement": str(digest.get("encouragement") or ""),
            "snippets": list(digest.get("snippets") or []),
            "checkins": int((digest.get("stats") or {}).get("checkins") or 0),
            "journal_entries": int((digest.get("stats") or {}).get("journal_entries") or 0),
            "somatic_sessions": int((digest.get("stats") or {}).get("somatic_sessions") or 0),
        },
    )
    await _create_in_app_notification(
        db,
        scoped_user_id,
        "Your 7-day digest is ready",
        "A personalized weekly meditation digest was generated with dynamic scripture snippets.",
        "weekly_digest_ready",
        {"email_status": email_status},
    )
    return {"status": "sent", "email_status": email_status, "digest": digest}


async def run_weekly_meditation_digest_dispatch(max_users: int = 120):
    db = get_db()
    now = datetime.now(timezone.utc)
    weekday = now.strftime("%a").lower()[:3]
    week_key = _week_key(now)

    users = await db.tv_dm_reminder_prefs.find(
        {
            "email_enabled": True,
            "weekly_lookback_day": weekday,
            "$or": [
                {"last_digest_week": {"$ne": week_key}},
                {"last_digest_week": {"$exists": False}},
            ],
        },
        {"_id": 0, "user_id": 1},
    ).limit(max_users).to_list(max_users)

    sent = 0
    skipped = 0
    failed = 0
    for row in users:
        user_id = str(row.get("user_id") or "")
        if not user_id:
            skipped += 1
            continue
        try:
            digest = await _build_weekly_digest_payload(db, user_id, 7)
            email_status = await _send_dm_email(
                db,
                user_id,
                digest["subject"],
                digest["html"],
                "daily_meditation_weekly_digest",
                template_payload={
                    "days": int(digest.get("days") or 7),
                    "dominant_theme": str((digest.get("stats") or {}).get("dominant_theme") or "steady"),
                    "headline": str(digest.get("headline") or ""),
                    "encouragement": str(digest.get("encouragement") or ""),
                    "snippets": list(digest.get("snippets") or []),
                    "checkins": int((digest.get("stats") or {}).get("checkins") or 0),
                    "journal_entries": int((digest.get("stats") or {}).get("journal_entries") or 0),
                    "somatic_sessions": int((digest.get("stats") or {}).get("somatic_sessions") or 0),
                },
            )
            if str(email_status).startswith("sent") or email_status == "sent":
                sent += 1
            else:
                skipped += 1

            await db.tv_dm_reminder_prefs.update_one(
                {"user_id": user_id},
                {"$set": {"last_digest_week": week_key, "last_digest_sent_at": _iso_now()}},
            )
        except Exception:
            failed += 1

    return {
        "status": "ok",
        "weekday": weekday,
        "week_key": week_key,
        "scanned": len(users),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
    }


@router.get("/notifications/{user_id}")
async def get_meditation_notifications(user_id: str, request: Request, unread_only: bool = False):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    query = {"user_id": scoped_user_id, "module": "daily_meditation"}
    if unread_only:
        query["read"] = False
    rows = await db.tv_notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    unread = await db.tv_notifications.count_documents({"user_id": scoped_user_id, "module": "daily_meditation", "read": False})
    return {"notifications": rows, "unread_count": int(unread)}


@router.post("/notifications/read")
async def mark_meditation_notifications_read(request: Request, user_id: str = Body(...), notification_timestamps: list[str] = Body(default_factory=list)):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    query = {"user_id": scoped_user_id, "module": "daily_meditation"}
    if notification_timestamps:
        query["created_at"] = {"$in": notification_timestamps}
    await db.tv_notifications.update_many(query, {"$set": {"read": True}})
    return {"status": "marked_read"}


@router.get("/compliance/export/{user_id}")
async def export_meditation_compliance(user_id: str, request: Request, format: Literal["json", "csv"] = Query(default="json")):
    db = get_db()
    _, scoped_user_id = await _resolve_scoped_user_id(request, user_id)
    plan = await _get_user_plan(db, scoped_user_id)
    quota = await _check_limit(db, scoped_user_id, plan, "dm_exports", "monthly_exports", "monthly")
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Monthly export limit reached for {plan} plan")

    checkins = await db.tv_dm_checkins.find({"user_id": scoped_user_id}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    journal = await db.tv_dm_journal.find({"user_id": scoped_user_id}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    somatic = await db.tv_dm_somatic_sessions.find({"user_id": scoped_user_id}, {"_id": 0}).sort("completed_at", -1).limit(500).to_list(500)
    reminders = await db.tv_dm_reminders.find({"user_id": scoped_user_id}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    community = await db.tv_dm_community_posts.find({"user_id": scoped_user_id}, {"_id": 0, "prayer_support_user_ids": 0}).sort("created_at", -1).limit(500).to_list(500)

    payload = {
        "generated_at": _iso_now(),
        "user_id": scoped_user_id,
        "plan": plan,
        "counts": {
            "checkins": len(checkins),
            "journal_entries": len(journal),
            "somatic_sessions": len(somatic),
            "reminders": len(reminders),
            "community_posts": len(community),
        },
        "data": {
            "checkins": checkins,
            "journal": journal,
            "somatic_sessions": somatic,
            "reminders": reminders,
            "community_posts": community,
        },
    }

    if format == "json":
        return payload

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "id", "timestamp", "summary"])
    for c in checkins:
        writer.writerow(["checkin", c.get("checkin_id"), c.get("created_at"), (c.get("heart_text") or "")[:120]])
    for j in journal:
        writer.writerow(["journal", j.get("entry_id"), j.get("created_at"), (j.get("title") or "")[:120]])
    for s in somatic:
        writer.writerow(["somatic", s.get("session_id"), s.get("completed_at"), s.get("invitation_id")])
    for r in reminders:
        writer.writerow(["reminder", r.get("reminder_id"), r.get("scheduled_for_iso"), r.get("status")])
    for p in community:
        writer.writerow(["community", p.get("post_id"), p.get("created_at"), (p.get("text") or "")[:120]])
    output.seek(0)

    filename = f"daily_meditation_compliance_{scoped_user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/safety/check")
async def safety_check(req: MeditationSafetyCheckRequest, request: Request):
    await _resolve_scoped_user_id(request, req.user_id)
    text = req.text.strip().lower()
    high_risk = any(term in text for term in HIGH_RISK_TERMS)
    if high_risk:
        return {
            "risk_level": "high",
            "message": "You may need immediate support. Please contact local emergency services or a crisis helpline now.",
            "resources": [
                "Local emergency number",
                "Nearest crisis hotline",
                "Trusted family, pastor, or counselor",
            ],
            "medical_disclaimer": "Daily Meditation supports reflection and does not replace professional care.",
        }

    supportive = "medium" if any(word in text for word in ["anxious", "panic", "burnout", "overwhelmed"]) else "low"
    return {
        "risk_level": supportive,
        "message": "Thank you for checking in. You can continue with gentle practices and ask for support anytime.",
        "resources": ["Breathing invitation", "Private journaling", "Community prayer support"],
        "medical_disclaimer": "Daily Meditation supports reflection and does not replace professional care.",
    }
