"""Lexicon Intelligence Hub (Word of the Day) for AI Feature Gallery.

Plan enforcement:
  Free    → Limited access
  Basic   → Almost unlimited access
  Premium → Full unlimited access
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import logging
import re
import uuid
import json
import csv
import io

from fastapi import APIRouter, HTTPException, Request, Query, Response
from pydantic import BaseModel, Field

from .db import User, db, require_auth
from utils.access_control_engine import build_session_entitlements, compute_effective_plan
from utils.llm_helper import generate_verified_json


router = APIRouter(prefix="/word-forge", tags=["Lexicon Intelligence Hub"])
logger = logging.getLogger("routes.word_forge")

FEATURE_ID = "lexicon-intelligence"
FEATURE_ROUTE = "/features/lexicon-intelligence"

ACTION_TO_ENTITLEMENT_KEY = {
    "generate_word": "word_forge_generate_word_daily",
    "quiz_attempt": "word_forge_quiz_attempt_daily",
    "save_word": "word_forge_save_word_daily",
    "review_complete": "word_forge_review_complete_daily",
    "usage_coach": "word_forge_usage_coach_daily",
    "business_brief": "word_forge_business_brief_daily",
    "challenge_submit": "word_forge_weekly_challenge_submit_daily",
}

PLAN_ACTION_LIMITS = {
    "generate_word": {"free": 4, "basic": 180, "premium": -1},
    "quiz_attempt": {"free": 12, "basic": 500, "premium": -1},
    "save_word": {"free": 24, "basic": 1000, "premium": -1},
    "review_complete": {"free": 15, "basic": 700, "premium": -1},
    "usage_coach": {"free": 6, "basic": 250, "premium": -1},
    "business_brief": {"free": 5, "basic": 220, "premium": -1},
    "challenge_submit": {"free": 2, "basic": 80, "premium": -1},
}

BATCH_SIZE_BY_PLAN = {
    "free": 2,
    "basic": 5,
    "premium": 8,
}

SNAPSHOT_LIMITS = {
    "free": 4,
    "basic": 20,
    "premium": -1,
}

TEMPLATE_LIBRARY = [
    {
        "template_id": "boardroom-brief",
        "title": "Boardroom Brief",
        "description": "Executive-grade vocabulary for concise leadership updates and strategy reviews.",
        "domain": "leadership",
        "difficulty": "advanced",
        "usage_context": "meeting",
        "business_context": "leadership",
        "target_outcome": "Sharper executive communication",
    },
    {
        "template_id": "sales-conversion-kit",
        "title": "Sales Conversion Kit",
        "description": "High-impact word paths for persuasive discovery calls and pitch follow-ups.",
        "domain": "business",
        "difficulty": "intermediate",
        "usage_context": "sales",
        "business_context": "sales",
        "target_outcome": "Higher client conversion confidence",
    },
    {
        "template_id": "cross-functional-ops",
        "title": "Cross-Functional Ops",
        "description": "Practical vocabulary for operations updates, trade-offs, and execution alignment.",
        "domain": "technology",
        "difficulty": "adaptive",
        "usage_context": "meeting",
        "business_context": "support",
        "target_outcome": "Faster decision clarity across teams",
    },
    {
        "template_id": "client-escalation-calm",
        "title": "Client Escalation Calm",
        "description": "De-escalation and trust-building wording for high-pressure support conversations.",
        "domain": "business",
        "difficulty": "beginner",
        "usage_context": "email",
        "business_context": "support",
        "target_outcome": "Calmer customer communications",
    },
    {
        "template_id": "negotiation-edge",
        "title": "Negotiation Edge",
        "description": "Precision vocabulary for negotiating trade-offs, concessions, and outcomes.",
        "domain": "legal",
        "difficulty": "advanced",
        "usage_context": "negotiation",
        "business_context": "leadership",
        "target_outcome": "Stronger strategic negotiations",
    },
]

REWARD_TIERS = [
    {
        "tier": "bronze",
        "min_points": 30,
        "label": "Bronze Communicator",
        "perk": "Unlock priority weekly word packs.",
    },
    {
        "tier": "silver",
        "min_points": 70,
        "label": "Silver Strategist",
        "perk": "Unlock advanced challenge prompts with deeper feedback.",
    },
    {
        "tier": "gold",
        "min_points": 120,
        "label": "Gold Executive",
        "perk": "Unlock executive phrase toolkit and spotlight placement.",
    },
]

ENTERPRISE_CAPABILITIES = [
    {
        "capability_id": "daily-word-brief",
        "title": "Daily lexical brief",
        "description": "Deliver one practical, high-impact word each day with direct workplace context.",
    },
    {
        "capability_id": "domain-calibration",
        "title": "Domain calibration",
        "description": "Switch between business, technology, legal, healthcare, and leadership vocabulary tracks.",
    },
    {
        "capability_id": "difficulty-modes",
        "title": "Difficulty progression",
        "description": "Adaptive, beginner, intermediate, and advanced learning intensity controls.",
    },
    {
        "capability_id": "pronunciation",
        "title": "Pronunciation intelligence",
        "description": "See IPA, syllable split, and speaking guidance for confident verbal usage.",
    },
    {
        "capability_id": "example-context",
        "title": "Context sentence library",
        "description": "Practice with realistic examples for email, meetings, negotiation, and client conversations.",
    },
    {
        "capability_id": "synonym-contrast",
        "title": "Synonym/antonym contrast",
        "description": "Learn adjacent words and precise opposite terms to avoid misuse.",
    },
    {
        "capability_id": "memory-hooks",
        "title": "Memory hooks",
        "description": "Use etymology and mnemonic prompts to improve retention speed.",
    },
    {
        "capability_id": "micro-challenges",
        "title": "Micro challenge engine",
        "description": "One-minute practical tasks that create fast daily learning habits.",
    },
    {
        "capability_id": "quiz-loop",
        "title": "Adaptive quiz loop",
        "description": "Validate understanding with instant scoring and correction feedback.",
    },
    {
        "capability_id": "usage-coach",
        "title": "Sentence usage coach",
        "description": "Evaluate how you used the word and receive rewrite recommendations.",
    },
    {
        "capability_id": "business-brief",
        "title": "Business communication brief",
        "description": "Generate word-ready snippets for emails, meetings, and sales interactions.",
    },
    {
        "capability_id": "save-vault",
        "title": "Personal lexical vault",
        "description": "Save words into a reusable knowledge bank for recurring review.",
    },
    {
        "capability_id": "spaced-review",
        "title": "Spaced review queue",
        "description": "Get intelligent review timing based on confidence scores.",
    },
    {
        "capability_id": "streak-performance",
        "title": "Streak and mastery tracking",
        "description": "Track consistency, XP, and mastery growth to sustain daily engagement.",
    },
    {
        "capability_id": "weekly-challenge-mode",
        "title": "Weekly challenge mode",
        "description": "Submit real-world usage entries each week to earn bonus points and progress badges.",
    },
    {
        "capability_id": "team-leaderboard",
        "title": "Team leaderboard",
        "description": "Compete on vocabulary execution points and rank against other active learners.",
    },
    {
        "capability_id": "reward-tier-progression",
        "title": "Reward tier progression",
        "description": "Unlock Bronze, Silver, and Gold perks based on weekly challenge performance.",
    },
    {
        "capability_id": "plan-ops-governance",
        "title": "Plan-aware governance",
        "description": "Auto-enforced Free/Basic/Premium limits with live quota telemetry.",
    },
]

FALLBACK_WORDS = [
    {
        "word": "Pragmatic",
        "part_of_speech": "adjective",
        "definition": "Focused on realistic and practical outcomes rather than theory alone.",
        "pronunciation": "prag-MAT-ik",
        "syllables": "prag-ma-tic",
        "etymology": "From Greek pragmatikos, meaning skilled in action.",
        "memory_hook": "Think: practical magic for real-world decisions.",
        "business_value": "Helps teams communicate implementation-first decisions with clarity.",
        "synonyms": ["practical", "realistic", "sensible", "workable"],
        "antonyms": ["idealistic", "impractical", "theoretical"],
        "examples": [
            "We chose a pragmatic rollout plan to reduce deployment risk.",
            "Her pragmatic feedback shortened our release cycle.",
            "A pragmatic proposal improved stakeholder alignment.",
        ],
        "micro_challenge": "Use 'pragmatic' in one sentence about today's top business decision.",
        "quiz": {
            "question": "Which sentence uses 'pragmatic' correctly?",
            "options": [
                "Our pragmatic launch prioritized low-risk milestones.",
                "The pragmatic painting looked very abstract.",
                "He pragmaticly forgot the deadline.",
                "Pragmatic means impossible to execute.",
            ],
            "correct_answer": "Our pragmatic launch prioritized low-risk milestones.",
            "explanation": "Pragmatic describes practical, actionable decisions.",
        },
    },
    {
        "word": "Catalyst",
        "part_of_speech": "noun",
        "definition": "A trigger that accelerates change or progress.",
        "pronunciation": "KAT-uh-list",
        "syllables": "cat-a-lyst",
        "etymology": "From Greek katalysis, meaning dissolution or loosening.",
        "memory_hook": "A catalyst is the spark that speeds everything up.",
        "business_value": "Useful in product, strategy, and growth conversations when describing momentum drivers.",
        "synonyms": ["trigger", "accelerator", "driver", "impetus"],
        "antonyms": ["barrier", "blocker", "slowdown"],
        "examples": [
            "Customer testimonials became a catalyst for conversion growth.",
            "The new onboarding flow was a catalyst for retention gains.",
            "Her proposal acted as a catalyst for faster approvals.",
        ],
        "micro_challenge": "Name one catalyst your team can deploy this week to improve output.",
        "quiz": {
            "question": "What does 'catalyst' mean in business communication?",
            "options": [
                "A driver that speeds change",
                "A delay in workflow",
                "A fixed budget line",
                "A meeting transcript",
            ],
            "correct_answer": "A driver that speeds change",
            "explanation": "Catalyst is commonly used for things that accelerate progress.",
        },
    },
    {
        "word": "Nuance",
        "part_of_speech": "noun",
        "definition": "A subtle distinction that adds precision to understanding.",
        "pronunciation": "NOO-ahns",
        "syllables": "nu-ance",
        "etymology": "From French, denoting slight shade of meaning.",
        "memory_hook": "Nuance is the tiny detail that changes the full picture.",
        "business_value": "Critical for negotiation, product positioning, and stakeholder communication.",
        "synonyms": ["subtlety", "distinction", "shade", "refinement"],
        "antonyms": ["simplicity", "bluntness", "generality"],
        "examples": [
            "The nuance in customer feedback changed our messaging strategy.",
            "Legal nuance affected contract interpretation.",
            "Pricing nuance helped us segment enterprise buyers.",
        ],
        "micro_challenge": "Identify one nuance in your current project brief that could affect delivery.",
        "quiz": {
            "question": "Which option best defines 'nuance'?",
            "options": [
                "A subtle but meaningful distinction",
                "A broad summary without detail",
                "A fixed process template",
                "An unrelated metric",
            ],
            "correct_answer": "A subtle but meaningful distinction",
            "explanation": "Nuance improves precision by capturing fine distinctions.",
        },
    },
]


class DailyWordRequest(BaseModel):
    domain: str = Field(default="business", max_length=40)
    difficulty: str = Field(default="adaptive", pattern="^(adaptive|beginner|intermediate|advanced)$")


class QuizSubmitRequest(BaseModel):
    word_id: str = Field(min_length=6, max_length=60)
    mode: str = Field(default="mcq", pattern="^(mcq|definition|usage)$")
    answer: str = Field(min_length=1, max_length=500)


class SavedToggleRequest(BaseModel):
    word_id: str = Field(min_length=6, max_length=60)
    save: bool = True


class ReviewCompleteRequest(BaseModel):
    word_id: str = Field(min_length=6, max_length=60)
    confidence: int = Field(ge=1, le=5)


class UsageCoachRequest(BaseModel):
    word_id: str = Field(min_length=6, max_length=60)
    sentence: str = Field(min_length=6, max_length=1200)
    context_type: str = Field(default="email", pattern="^(email|meeting|sales|negotiation|presentation)$")


class BusinessBriefRequest(BaseModel):
    word_id: str = Field(min_length=6, max_length=60)
    context_type: str = Field(default="meeting", pattern="^(meeting|email|sales|leadership|support)$")


class ChallengeSubmitRequest(BaseModel):
    word_id: str | None = Field(default=None, max_length=60)
    submission_text: str = Field(min_length=8, max_length=1600)


class BatchGenerateRequest(BaseModel):
    template_id: str | None = Field(default=None, max_length=60)
    domains: list[str] | None = Field(default=None, min_length=1, max_length=8)
    difficulty: str = Field(default="adaptive", pattern="^(adaptive|beginner|intermediate|advanced)$")


class SnapshotCreateRequest(BaseModel):
    name: str = Field(default="", max_length=90)
    include_saved_words: bool = True
    include_leaderboard: bool = False


class SnapshotRestoreRequest(BaseModel):
    snapshot_id: str = Field(min_length=8, max_length=60)


class TemplateApplyRequest(BaseModel):
    template_id: str = Field(min_length=3, max_length=60)


def _resolve_plan(user: User) -> str:
    plan = compute_effective_plan(_build_user_doc(user))
    return plan if plan in {"free", "basic", "premium"} else "free"


def _scope_label(plan: str) -> str:
    if plan == "premium":
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


def _template_by_id(template_id: str | None) -> dict[str, Any] | None:
    target = str(template_id or "").strip()
    if not target:
        return None
    return next((item for item in TEMPLATE_LIBRARY if item.get("template_id") == target), None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_floor_iso() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", str(value or "").lower())).strip()


def _word_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "word_id": 1,
        "domain": 1,
        "difficulty": 1,
        "word": 1,
        "part_of_speech": 1,
        "definition": 1,
        "pronunciation": 1,
        "syllables": 1,
        "etymology": 1,
        "memory_hook": 1,
        "business_value": 1,
        "synonyms": 1,
        "antonyms": 1,
        "examples": 1,
        "micro_challenge": 1,
        "quiz": 1,
        "source": 1,
        "day_key": 1,
        "created_at": 1,
    }


async def _ensure_feature_registry_entry() -> None:
    now = _now_iso()
    max_order = await db.feature_registry.find_one({}, {"_id": 0, "sort_order": 1}, sort=[("sort_order", -1)])
    sort_order = (int(max_order.get("sort_order") or 0) + 1) if max_order else 0
    feature_doc = {
        "feature_id": FEATURE_ID,
        "title": "Lexicon Intelligence Hub",
        "description": "Master high-impact vocabulary daily with business-ready communication drills and review automation.",
        "icon": "book",
        "route": FEATURE_ROUTE,
        "category": "productivity",
        "color": "#14B8A6",
        "is_new": True,
        "premium": False,
        "enabled": True,
        "sort_order": sort_order,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.feature_registry.update_one(
        {"feature_id": FEATURE_ID},
        {"$setOnInsert": feature_doc},
        upsert=True,
    )
    if not result.upserted_id:
        return

    try:
        from routes import feature_registry as feature_registry_route

        feature_registry_route._registry_cache["ts"] = 0
    except Exception as exc:
        logger.warning(f"Word Forge cache invalidation warning: {exc}")

    try:
        from utils.ws_manager import broadcast_data_change

        await broadcast_data_change("features", "created")
    except Exception as exc:
        logger.warning(f"Word Forge websocket broadcast warning: {exc}")

    try:
        from routes.global_platform_state import sync_global_features

        await sync_global_features(
            reason="Lexicon Intelligence Hub auto-registration",
            actor_user_id="",
            event_type="FeatureAdded",
        )
    except Exception as exc:
        logger.warning(f"Word Forge GPS sync warning: {exc}")


def _build_user_doc(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "full_access": bool(user.full_access),
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "payment_verified": bool(getattr(user, "payment_verified", False)),
        "subscription_end_date": user.subscription_end_date,
        "subscription_permanent": bool(user.subscription_permanent),
        "platform_role": user.platform_role,
        "employee_permissions": list(user.employee_permissions or []),
        "pending_subscription_transition": user.pending_subscription_transition,
    }


async def _enforce_action_limit(user: User, action: str) -> dict[str, Any]:
    plan = _resolve_plan(user)
    if action not in ACTION_TO_ENTITLEMENT_KEY:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    entitlement_key = ACTION_TO_ENTITLEMENT_KEY[action]
    entitlements = build_session_entitlements(_build_user_doc(user)).get("feature_entitlements") or {}
    limit = entitlements.get(entitlement_key)
    if not isinstance(limit, int):
        limit = int((PLAN_ACTION_LIMITS.get(action) or {}).get(plan, 0))

    used = await db.word_forge_usage_log.count_documents(
        {
            "user_id": user.user_id,
            "action": action,
            "created_at": {"$gte": _today_floor_iso()},
        }
    )

    if int(limit) >= 0 and int(used) >= int(limit):
        raise HTTPException(
            status_code=429,
            detail=(
                f"{_scope_label(plan)}: daily {action.replace('_', ' ')} limit reached "
                f"({int(limit)}). Upgrade plan for additional capacity."
            ),
        )

    return {
        "plan": plan,
        "scope_label": _scope_label(plan),
        "used": int(used),
        "limit": int(limit),
        "remaining": -1 if int(limit) < 0 else max(0, int(limit) - int(used)),
    }


async def _log_usage(user_id: str, action: str, plan: str, metadata: dict[str, Any] | None = None) -> None:
    await db.word_forge_usage_log.insert_one(
        {
            "usage_id": f"wf_usage_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "action": action,
            "plan": plan,
            "metadata": metadata or {},
            "created_at": _now_iso(),
        }
    )


async def _limits_snapshot(user: User) -> dict[str, int]:
    plan = _resolve_plan(user)
    entitlements = build_session_entitlements(_build_user_doc(user)).get("feature_entitlements") or {}
    snapshot: dict[str, int] = {}
    for action, key in ACTION_TO_ENTITLEMENT_KEY.items():
        val = entitlements.get(key)
        if isinstance(val, int):
            snapshot[action] = int(val)
        else:
            snapshot[action] = int((PLAN_ACTION_LIMITS.get(action) or {}).get(plan, 0))
    return snapshot


def _export_payload_to_csv(payload: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "key", "value", "meta"])

    profile = payload.get("profile") or {}
    for key, value in profile.items():
        writer.writerow(["profile", key, value, ""])

    usage_summary = payload.get("usage_summary") or {}
    today_usage = usage_summary.get("today_usage") or {}
    for key, value in today_usage.items():
        writer.writerow(["today_usage", key, value, ""])

    for item in (payload.get("saved_words") or [])[:200]:
        writer.writerow([
            "saved_words",
            item.get("word", ""),
            item.get("mastery_score", 0),
            f"reviews={item.get('review_count', 0)}",
        ])

    for item in (payload.get("recent_words") or [])[:200]:
        writer.writerow([
            "recent_words",
            item.get("word", ""),
            item.get("domain", ""),
            item.get("difficulty", ""),
        ])

    challenge_entry = payload.get("weekly_challenge_entry") or {}
    for key in ["points", "rank", "tier", "tier_label", "submissions"]:
        writer.writerow(["weekly_challenge", key, challenge_entry.get(key, ""), ""])

    return output.getvalue()


async def _build_recommendations(user: User, review_queue: list[dict[str, Any]], saved_words_count: int) -> list[dict[str, Any]]:
    usage_summary = await _build_usage_summary(user.user_id)
    profile = await _update_profile(user.user_id, xp_delta=0)
    today_usage = usage_summary.get("today_usage") or {}

    recommendations: list[dict[str, Any]] = []
    if review_queue:
        recommendations.append(
            {
                "recommendation_id": "clear-review-queue",
                "priority": "high",
                "title": "Clear your review queue",
                "reason": f"{len(review_queue)} words are due now. Reviewing them compounds retention.",
                "cta": "Run 2 confidence reviews",
            }
        )

    if int(today_usage.get("quiz_attempt") or 0) < 3:
        recommendations.append(
            {
                "recommendation_id": "quiz-boost",
                "priority": "high",
                "title": "Do a quick quiz sprint",
                "reason": "Daily quiz loops improve recall speed and applied usage quality.",
                "cta": "Complete 3 quiz attempts",
            }
        )

    if saved_words_count < 10:
        recommendations.append(
            {
                "recommendation_id": "vault-growth",
                "priority": "medium",
                "title": "Grow your lexical vault",
                "reason": "A larger vault improves spaced-review effectiveness and personalization.",
                "cta": "Save 3 high-impact words",
            }
        )

    if int(profile.get("streak_days") or 0) < 3:
        recommendations.append(
            {
                "recommendation_id": "streak-foundation",
                "priority": "medium",
                "title": "Build a 3-day streak",
                "reason": "Early streak consistency is the strongest predictor of mastery growth.",
                "cta": "Generate one word daily for 3 days",
            }
        )

    if not recommendations:
        recommendations.append(
            {
                "recommendation_id": "challenge-upshift",
                "priority": "medium",
                "title": "Push weekly challenge points",
                "reason": "You are on track—challenge submissions now can unlock next-tier perks.",
                "cta": "Submit one weekly challenge entry",
            }
        )

    return recommendations[:5]


def _pick_fallback_word(domain: str) -> dict[str, Any]:
    seed = f"{domain}-{_today_key()}"
    idx = abs(hash(seed)) % len(FALLBACK_WORDS)
    return FALLBACK_WORDS[idx]


def _normalize_word_payload(raw: dict[str, Any], domain: str, difficulty: str) -> dict[str, Any]:
    fallback = _pick_fallback_word(domain)
    payload = raw if isinstance(raw, dict) else {}

    word = str(payload.get("word") or fallback["word"]).strip().title()
    synonyms = payload.get("synonyms") if isinstance(payload.get("synonyms"), list) else fallback["synonyms"]
    antonyms = payload.get("antonyms") if isinstance(payload.get("antonyms"), list) else fallback["antonyms"]
    examples = payload.get("examples") if isinstance(payload.get("examples"), list) else fallback["examples"]
    quiz = payload.get("quiz") if isinstance(payload.get("quiz"), dict) else fallback["quiz"]
    options = quiz.get("options") if isinstance(quiz.get("options"), list) else fallback["quiz"]["options"]
    options = [str(item).strip() for item in options if str(item).strip()][:4]

    correct_answer = str(quiz.get("correct_answer") or fallback["quiz"]["correct_answer"]).strip()
    if correct_answer not in options:
        if options:
            options[0] = correct_answer
        else:
            options = [correct_answer]

    if len(options) < 4:
        fallback_options = [opt for opt in fallback["quiz"]["options"] if opt not in options]
        options.extend(fallback_options[: max(0, 4 - len(options))])

    return {
        "word": word,
        "part_of_speech": str(payload.get("part_of_speech") or fallback["part_of_speech"]).strip().lower(),
        "definition": str(payload.get("definition") or fallback["definition"]).strip(),
        "pronunciation": str(payload.get("pronunciation") or fallback["pronunciation"]).strip(),
        "syllables": str(payload.get("syllables") or fallback["syllables"]).strip(),
        "etymology": str(payload.get("etymology") or fallback["etymology"]).strip(),
        "memory_hook": str(payload.get("memory_hook") or fallback["memory_hook"]).strip(),
        "business_value": str(payload.get("business_value") or fallback["business_value"]).strip(),
        "synonyms": [str(item).strip() for item in synonyms if str(item).strip()][:6],
        "antonyms": [str(item).strip() for item in antonyms if str(item).strip()][:6],
        "examples": [str(item).strip() for item in examples if str(item).strip()][:4],
        "micro_challenge": str(payload.get("micro_challenge") or fallback["micro_challenge"]).strip(),
        "quiz": {
            "question": str(quiz.get("question") or fallback["quiz"]["question"]).strip(),
            "options": options,
            "correct_answer": correct_answer,
            "explanation": str(quiz.get("explanation") or fallback["quiz"]["explanation"]).strip(),
        },
        "domain": domain,
        "difficulty": difficulty,
    }


async def _generate_word_payload(domain: str, difficulty: str, user_id: str) -> tuple[dict[str, Any], str]:
    prompt = f"""
Generate one professional "word of the day" for domain={domain} and difficulty={difficulty}.

Return ONLY valid JSON with this exact structure:
{{
  "word": "single word",
  "part_of_speech": "noun|verb|adjective|adverb",
  "definition": "clear definition in one sentence",
  "pronunciation": "phonetic text",
  "syllables": "syllable-split",
  "etymology": "short origin note",
  "memory_hook": "easy memory prompt",
  "business_value": "why this word is useful in business communication",
  "synonyms": ["...", "...", "..."],
  "antonyms": ["...", "..."],
  "examples": [
    "email example sentence",
    "meeting example sentence",
    "leadership example sentence"
  ],
  "micro_challenge": "short task",
  "quiz": {{
    "question": "mcq question",
    "options": ["A", "B", "C", "D"],
    "correct_answer": "one option exactly",
    "explanation": "why that option is right"
  }}
}}
"""
    try:
        generated = await generate_verified_json(
            prompt,
            "You are an enterprise vocabulary strategist. Return strict JSON only.",
            f"word-forge-{user_id}-{uuid.uuid4().hex[:8]}",
        )
        return _normalize_word_payload(generated if isinstance(generated, dict) else {}, domain, difficulty), "llm"
    except Exception as exc:
        logger.warning(f"Word Forge LLM generation fallback: {exc}")
        return _normalize_word_payload({}, domain, difficulty), "fallback"


async def _create_word_entry(user: User, domain: str, difficulty: str) -> dict[str, Any]:
    normalized_domain = re.sub(r"[^a-z\-]", "", str(domain or "business").lower()) or "business"
    normalized_difficulty = difficulty if difficulty in {"adaptive", "beginner", "intermediate", "advanced"} else "adaptive"
    payload, source = await _generate_word_payload(normalized_domain, normalized_difficulty, user.user_id)
    word_doc = {
        "word_id": f"wf_word_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "day_key": _today_key(),
        "domain": normalized_domain,
        "difficulty": normalized_difficulty,
        "word": payload["word"],
        "part_of_speech": payload["part_of_speech"],
        "definition": payload["definition"],
        "pronunciation": payload["pronunciation"],
        "syllables": payload["syllables"],
        "etymology": payload["etymology"],
        "memory_hook": payload["memory_hook"],
        "business_value": payload["business_value"],
        "synonyms": payload["synonyms"],
        "antonyms": payload["antonyms"],
        "examples": payload["examples"],
        "micro_challenge": payload["micro_challenge"],
        "quiz": payload["quiz"],
        "source": source,
        "created_at": _now_iso(),
    }
    await db.word_forge_words.insert_one(word_doc)
    return {k: v for k, v in word_doc.items() if k not in {"user_id", "_id"}}


async def _get_or_create_today_word(user: User) -> dict[str, Any]:
    existing = await db.word_forge_words.find_one(
        {"user_id": user.user_id, "day_key": _today_key()},
        _word_projection(),
        sort=[("created_at", -1)],
    )
    if existing:
        safe_existing = dict(existing)
        safe_existing.pop("_id", None)
        return safe_existing
    return await _create_word_entry(user, domain="business", difficulty="adaptive")


async def _update_profile(
    user_id: str,
    *,
    xp_delta: int = 0,
    mastered_delta: int = 0,
) -> dict[str, Any]:
    today = _today_key()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    profile = await db.word_forge_profiles.find_one({"user_id": user_id}, {"_id": 0})

    if not profile:
        profile = {
            "profile_id": f"wf_profile_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "streak_days": 0,
            "xp_total": 0,
            "words_mastered": 0,
            "last_active_day": "",
            "updated_at": _now_iso(),
        }

    streak_days = int(profile.get("streak_days") or 0)
    last_active_day = str(profile.get("last_active_day") or "")

    if last_active_day == today:
        next_streak = streak_days
    elif last_active_day == yesterday:
        next_streak = streak_days + 1
    else:
        next_streak = 1

    next_profile = {
        "profile_id": profile.get("profile_id") or f"wf_profile_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "streak_days": max(1, int(next_streak)),
        "xp_total": max(0, int(profile.get("xp_total") or 0) + int(xp_delta)),
        "words_mastered": max(0, int(profile.get("words_mastered") or 0) + int(mastered_delta)),
        "last_active_day": today,
        "updated_at": _now_iso(),
    }
    await db.word_forge_profiles.update_one({"user_id": user_id}, {"$set": next_profile}, upsert=True)
    return next_profile


async def _build_usage_summary(user_id: str) -> dict[str, Any]:
    today_usage = await db.word_forge_usage_log.aggregate(
        [
            {"$match": {"user_id": user_id, "created_at": {"$gte": _today_floor_iso()}}},
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        ]
    ).to_list(100)
    usage_map = {str(row.get("_id") or ""): int(row.get("count") or 0) for row in today_usage}

    words_generated_30d = await db.word_forge_words.count_documents(
        {
            "user_id": user_id,
            "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()},
        }
    )
    saved_count = await db.word_forge_saved.count_documents({"user_id": user_id})
    return {
        "today_usage": usage_map,
        "words_generated_30d": int(words_generated_30d),
        "saved_words": int(saved_count),
    }


def _week_key() -> str:
    iso = datetime.now(timezone.utc).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_end_iso() -> str:
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    days_until_sunday_end = 6 - weekday
    end = now.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days_until_sunday_end)
    return end.isoformat()


def _mask_identifier(name: str, email: str) -> str:
    if name and str(name).strip():
        return str(name).strip()
    local = str(email or "").split("@")[0]
    if not local:
        return "Anonymous"
    if len(local) <= 3:
        return f"{local[0]}***"
    return f"{local[:3]}***"


def _reward_tier_for_points(points: int) -> dict[str, Any]:
    normalized = max(0, int(points))
    reached = [tier for tier in REWARD_TIERS if normalized >= int(tier.get("min_points") or 0)]
    if not reached:
        return {
            "tier": "starter",
            "label": "Starter",
            "next_tier": REWARD_TIERS[0],
            "perks_unlocked": [],
        }

    current = reached[-1]
    next_tier = next((tier for tier in REWARD_TIERS if int(tier.get("min_points") or 0) > normalized), None)
    return {
        "tier": str(current.get("tier") or "starter"),
        "label": str(current.get("label") or "Starter"),
        "next_tier": next_tier,
        "perks_unlocked": [str(item.get("perk") or "") for item in reached if str(item.get("perk") or "")],
    }


async def _ensure_weekly_challenge() -> dict[str, Any]:
    key = _week_key()
    challenge = await db.word_forge_challenges.find_one({"week_key": key}, {"_id": 0})
    if challenge:
        if not challenge.get("reward_tiers"):
            await db.word_forge_challenges.update_one(
                {"challenge_id": challenge.get("challenge_id")},
                {"$set": {"reward_tiers": REWARD_TIERS, "updated_at": _now_iso()}},
            )
            challenge = await db.word_forge_challenges.find_one({"week_key": key}, {"_id": 0})
        return challenge

    now = _now_iso()
    challenge_doc = {
        "challenge_id": f"wf_ch_{key.lower().replace('-', '').replace('w', 'wk')}",
        "week_key": key,
        "title": "Weekly Vocabulary Impact Challenge",
        "objective": "Submit real-world sentence applications using your weekly words to earn leaderboard points.",
        "reward": "Top 3 earn elite communication streak badges and leaderboard spotlight.",
        "reward_tiers": REWARD_TIERS,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "ends_at": _week_end_iso(),
    }
    await db.word_forge_challenges.update_one(
        {"week_key": key},
        {"$setOnInsert": challenge_doc},
        upsert=True,
    )
    saved = await db.word_forge_challenges.find_one({"week_key": key}, {"_id": 0})
    return saved or challenge_doc


async def _get_challenge_entry(user_id: str, challenge_id: str) -> dict[str, Any] | None:
    return await db.word_forge_challenge_entries.find_one(
        {"user_id": user_id, "challenge_id": challenge_id},
        {"_id": 0},
    )


async def _get_weekly_leaderboard(challenge_id: str, limit: int = 20) -> list[dict[str, Any]]:
    entries = await db.word_forge_challenge_entries.find(
        {"challenge_id": challenge_id},
        {"_id": 0, "user_id": 1, "points": 1, "submissions": 1, "updated_at": 1, "tier": 1, "perks_unlocked": 1},
    ).sort([("points", -1), ("updated_at", 1)]).limit(limit).to_list(limit)

    if not entries:
        return []

    user_ids = [str(item.get("user_id") or "") for item in entries if item.get("user_id")]
    user_rows = await db.users.find(
        {"user_id": {"$in": user_ids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1},
    ).to_list(max(1, len(user_ids)))
    user_map = {str(row.get("user_id") or ""): row for row in user_rows}

    leaderboard: list[dict[str, Any]] = []
    for idx, item in enumerate(entries, start=1):
        user_id = str(item.get("user_id") or "")
        user_row = user_map.get(user_id) or {}
        points = int(item.get("points") or 0)
        tier_info = _reward_tier_for_points(points)
        leaderboard.append(
            {
                "rank": idx,
                "user_id": user_id,
                "display_name": _mask_identifier(str(user_row.get("name") or ""), str(user_row.get("email") or "")),
                "points": points,
                "submissions": int(item.get("submissions") or 0),
                "tier": str(item.get("tier") or tier_info.get("tier") or "starter"),
                "tier_label": str(tier_info.get("label") or "Starter"),
                "perks_unlocked": item.get("perks_unlocked") if isinstance(item.get("perks_unlocked"), list) else tier_info.get("perks_unlocked", []),
                "updated_at": item.get("updated_at"),
            }
        )
    return leaderboard


async def _get_user_challenge_rank(challenge_id: str, user_id: str) -> int | None:
    entry = await db.word_forge_challenge_entries.find_one(
        {"challenge_id": challenge_id, "user_id": user_id},
        {"_id": 0, "points": 1},
    )
    if not entry:
        return None
    points = int(entry.get("points") or 0)
    higher = await db.word_forge_challenge_entries.count_documents(
        {"challenge_id": challenge_id, "points": {"$gt": points}}
    )
    return int(higher) + 1


@router.get("/health")
async def word_forge_health():
    return {"status": "healthy", "feature": "Lexicon Intelligence Hub", "feature_id": FEATURE_ID}


@router.get("/templates")
async def list_templates(request: Request):
    user = await require_auth(request)
    plan = _resolve_plan(user)
    recommended = ["cross-functional-ops", "sales-conversion-kit"]
    if plan == "premium":
        recommended = ["boardroom-brief", "negotiation-edge", "sales-conversion-kit"]
    elif plan == "free":
        recommended = ["cross-functional-ops", "client-escalation-calm"]
    return {
        "feature_id": FEATURE_ID,
        "plan": plan,
        "templates": TEMPLATE_LIBRARY,
        "recommended_template_ids": recommended,
        "generated_at": _now_iso(),
    }


@router.post("/templates/apply")
async def apply_template(payload: TemplateApplyRequest, request: Request):
    user = await require_auth(request)
    template = _template_by_id(payload.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    now = _now_iso()
    prefs = {
        "user_id": user.user_id,
        "template_id": template.get("template_id"),
        "domain": template.get("domain"),
        "difficulty": template.get("difficulty"),
        "usage_context": template.get("usage_context"),
        "business_context": template.get("business_context"),
        "updated_at": now,
    }
    await db.word_forge_preferences.update_one({"user_id": user.user_id}, {"$set": prefs}, upsert=True)
    return {"status": "applied", "template": template, "updated_at": now}


@router.post("/batch/generate")
async def batch_generate_words(payload: BatchGenerateRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "generate_word")
    plan = quota["plan"]
    template = _template_by_id(payload.template_id)
    max_batch = int(BATCH_SIZE_BY_PLAN.get(plan, 2))

    raw_domains = payload.domains or []
    cleaned_domains = [
        re.sub(r"[^a-z\-]", "", str(item or "").lower())
        for item in raw_domains
        if str(item or "").strip()
    ]
    if not cleaned_domains:
        cleaned_domains = [str((template or {}).get("domain") or "business")]

    cleaned_domains = [item for item in cleaned_domains if item] or ["business"]
    remaining = int(quota["remaining"])
    allowed_by_quota = max_batch if int(quota["limit"]) < 0 else max(0, min(max_batch, remaining))
    count = min(len(cleaned_domains), allowed_by_quota)
    if count <= 0:
        raise HTTPException(status_code=429, detail="Daily generate word limit reached for your plan")

    job_id = f"wf_batch_{uuid.uuid4().hex[:12]}"
    selected_domains = cleaned_domains[:count]
    difficulty = str(payload.difficulty or (template or {}).get("difficulty") or "adaptive")
    words: list[dict[str, Any]] = []

    for domain in selected_domains:
        word = await _create_word_entry(user, domain=domain, difficulty=difficulty)
        words.append(word)
        await _log_usage(
            user.user_id,
            "generate_word",
            plan,
            {"word_id": word.get("word_id"), "domain": domain, "batch_job_id": job_id},
        )

    profile = await _update_profile(user.user_id, xp_delta=3 * len(words))
    now = _now_iso()
    job_doc = {
        "job_id": job_id,
        "user_id": user.user_id,
        "template_id": (template or {}).get("template_id"),
        "domains": selected_domains,
        "difficulty": difficulty,
        "status": "completed",
        "word_ids": [item.get("word_id") for item in words if item.get("word_id")],
        "count": len(words),
        "created_at": now,
        "updated_at": now,
    }
    await db.word_forge_batch_jobs.insert_one(job_doc)

    refreshed_usage = await db.word_forge_usage_log.count_documents(
        {
            "user_id": user.user_id,
            "action": "generate_word",
            "created_at": {"$gte": _today_floor_iso()},
        }
    )
    limit = int(quota["limit"])
    return {
        "status": "completed",
        "job": {k: v for k, v in job_doc.items() if k not in {"user_id", "_id"}},
        "words": words,
        "quota": {
            **quota,
            "used": int(refreshed_usage),
            "remaining": -1 if limit < 0 else max(0, limit - int(refreshed_usage)),
        },
        "profile": profile,
    }


@router.get("/batch/jobs")
async def list_batch_jobs(request: Request, limit: int = Query(default=20, ge=1, le=50)):
    user = await require_auth(request)
    rows = await db.word_forge_batch_jobs.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "job_id": 1,
            "template_id": 1,
            "domains": 1,
            "difficulty": 1,
            "status": 1,
            "count": 1,
            "word_ids": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"jobs": rows, "count": len(rows)}


@router.post("/snapshots")
async def create_workspace_snapshot(payload: SnapshotCreateRequest, request: Request):
    user = await require_auth(request)
    plan = _resolve_plan(user)
    snapshot_limit = int(SNAPSHOT_LIMITS.get(plan, 4))
    existing_count = await db.word_forge_snapshots.count_documents({"user_id": user.user_id})
    if snapshot_limit >= 0 and int(existing_count) >= snapshot_limit:
        raise HTTPException(status_code=429, detail="Snapshot limit reached for your plan")

    daily_word = await _get_or_create_today_word(user)
    profile = await _update_profile(user.user_id, xp_delta=0)
    usage_summary = await _build_usage_summary(user.user_id)
    weekly_challenge = await _ensure_weekly_challenge()
    challenge_entry = await _get_challenge_entry(user.user_id, weekly_challenge.get("challenge_id"))
    challenge_rank = await _get_user_challenge_rank(weekly_challenge.get("challenge_id"), user.user_id)

    saved_words: list[dict[str, Any]] = []
    if bool(payload.include_saved_words):
        saved_words = await db.word_forge_saved.find(
            {"user_id": user.user_id},
            {
                "_id": 0,
                "word_id": 1,
                "word": 1,
                "part_of_speech": 1,
                "definition": 1,
                "next_review_at": 1,
                "review_count": 1,
                "mastery_score": 1,
                "saved_at": 1,
                "updated_at": 1,
            },
        ).sort("updated_at", -1).limit(120).to_list(120)

    leaderboard: list[dict[str, Any]] = []
    if bool(payload.include_leaderboard):
        leaderboard = await _get_weekly_leaderboard(weekly_challenge.get("challenge_id"), limit=15)

    now = _now_iso()
    snapshot_id = f"wf_snapshot_{uuid.uuid4().hex[:12]}"
    snapshot_name = str(payload.name or "").strip() or f"Workspace Snapshot {datetime.now(timezone.utc).strftime('%d %b %H:%M')}"

    snapshot_doc = {
        "snapshot_id": snapshot_id,
        "user_id": user.user_id,
        "name": snapshot_name,
        "plan": plan,
        "saved_words_count": len(saved_words),
        "payload": {
            "daily_word": daily_word,
            "profile": profile,
            "usage_summary": usage_summary,
            "saved_words": saved_words,
            "weekly_challenge": weekly_challenge,
            "weekly_challenge_entry": {
                **({k: v for k, v in (challenge_entry or {}).items()} if challenge_entry else {}),
                "rank": challenge_rank,
            },
            "leaderboard_preview": leaderboard,
        },
        "created_at": now,
        "updated_at": now,
    }
    await db.word_forge_snapshots.insert_one(snapshot_doc)
    return {
        "status": "created",
        "snapshot": {
            "snapshot_id": snapshot_id,
            "name": snapshot_name,
            "plan": plan,
            "saved_words_count": len(saved_words),
            "created_at": now,
        },
    }


@router.get("/snapshots")
async def list_workspace_snapshots(request: Request, limit: int = Query(default=20, ge=1, le=60)):
    user = await require_auth(request)
    rows = await db.word_forge_snapshots.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "snapshot_id": 1,
            "name": 1,
            "plan": 1,
            "saved_words_count": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"snapshots": rows, "count": len(rows)}


@router.post("/snapshots/restore")
async def restore_workspace_snapshot(payload: SnapshotRestoreRequest, request: Request):
    user = await require_auth(request)
    snapshot = await db.word_forge_snapshots.find_one(
        {"snapshot_id": payload.snapshot_id, "user_id": user.user_id},
        {"_id": 0},
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    content = snapshot.get("payload") or {}
    restored_saved = 0
    for item in (content.get("saved_words") or [])[:150]:
        if not isinstance(item, dict):
            continue
        word_id = str(item.get("word_id") or "").strip()
        if not word_id:
            continue
        row = {
            "saved_id": f"wf_saved_{uuid.uuid4().hex[:10]}",
            "user_id": user.user_id,
            "word_id": word_id,
            "word": str(item.get("word") or "").strip(),
            "part_of_speech": str(item.get("part_of_speech") or "").strip(),
            "definition": str(item.get("definition") or "").strip(),
            "next_review_at": str(item.get("next_review_at") or _now_iso()),
            "review_count": int(item.get("review_count") or 0),
            "mastery_score": int(item.get("mastery_score") or 0),
            "saved_at": str(item.get("saved_at") or _now_iso()),
            "updated_at": _now_iso(),
        }
        await db.word_forge_saved.update_one(
            {"user_id": user.user_id, "word_id": word_id},
            {"$set": row},
            upsert=True,
        )
        restored_saved += 1

    restored_word = None
    daily_word = content.get("daily_word") if isinstance(content.get("daily_word"), dict) else None
    if daily_word:
        restored_word = {
            "word_id": f"wf_word_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "day_key": _today_key(),
            "domain": str(daily_word.get("domain") or "business"),
            "difficulty": str(daily_word.get("difficulty") or "adaptive"),
            "word": str(daily_word.get("word") or "").strip().title(),
            "part_of_speech": str(daily_word.get("part_of_speech") or "").strip(),
            "definition": str(daily_word.get("definition") or "").strip(),
            "pronunciation": str(daily_word.get("pronunciation") or "").strip(),
            "syllables": str(daily_word.get("syllables") or "").strip(),
            "etymology": str(daily_word.get("etymology") or "").strip(),
            "memory_hook": str(daily_word.get("memory_hook") or "").strip(),
            "business_value": str(daily_word.get("business_value") or "").strip(),
            "synonyms": [str(x).strip() for x in (daily_word.get("synonyms") or []) if str(x).strip()][:6],
            "antonyms": [str(x).strip() for x in (daily_word.get("antonyms") or []) if str(x).strip()][:6],
            "examples": [str(x).strip() for x in (daily_word.get("examples") or []) if str(x).strip()][:4],
            "micro_challenge": str(daily_word.get("micro_challenge") or "").strip(),
            "quiz": daily_word.get("quiz") if isinstance(daily_word.get("quiz"), dict) else {},
            "source": "snapshot-restore",
            "created_at": _now_iso(),
        }
        await db.word_forge_words.insert_one(restored_word)

    await _log_usage(
        user.user_id,
        "review_complete",
        _resolve_plan(user),
        {"snapshot_id": payload.snapshot_id, "restored_saved_words": restored_saved},
    )

    return {
        "status": "restored",
        "snapshot_id": payload.snapshot_id,
        "restored_saved_words": restored_saved,
        "active_word": {k: v for k, v in (restored_word or {}).items() if k not in {"_id", "user_id"}},
        "restored_at": _now_iso(),
    }


@router.get("/recommendations")
async def workspace_recommendations(request: Request):
    user = await require_auth(request)
    saved_words = await db.word_forge_saved.find(
        {"user_id": user.user_id},
        {"_id": 0, "word_id": 1, "next_review_at": 1},
    ).to_list(200)
    now_iso = _now_iso()
    review_queue = [row for row in saved_words if not row.get("next_review_at") or str(row.get("next_review_at")) <= now_iso]
    recommendations = await _build_recommendations(user, review_queue, len(saved_words))
    return {
        "feature_id": FEATURE_ID,
        "recommendations": recommendations,
        "generated_at": _now_iso(),
    }


@router.get("/export")
async def export_workspace(
    request: Request,
    format: str = Query(default="payload", pattern="^(payload|json|csv)$"),
):
    user = await require_auth(request)
    plan = _resolve_plan(user)
    profile = await _update_profile(user.user_id, xp_delta=0)
    usage_summary = await _build_usage_summary(user.user_id)
    saved_words = await db.word_forge_saved.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "word_id": 1,
            "word": 1,
            "part_of_speech": 1,
            "definition": 1,
            "next_review_at": 1,
            "review_count": 1,
            "mastery_score": 1,
            "saved_at": 1,
            "updated_at": 1,
        },
    ).sort("updated_at", -1).limit(150).to_list(150)
    recent_words = await db.word_forge_words.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "word_id": 1,
            "word": 1,
            "domain": 1,
            "difficulty": 1,
            "created_at": 1,
            "source": 1,
        },
    ).sort("created_at", -1).limit(80).to_list(80)

    challenge = await _ensure_weekly_challenge()
    challenge_entry = await _get_challenge_entry(user.user_id, challenge.get("challenge_id"))
    challenge_rank = await _get_user_challenge_rank(challenge.get("challenge_id"), user.user_id)
    challenge_points = int((challenge_entry or {}).get("points") or 0)
    challenge_tier = _reward_tier_for_points(challenge_points)

    payload = {
        "feature_id": FEATURE_ID,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "profile": profile,
        "usage_summary": usage_summary,
        "saved_words": saved_words,
        "recent_words": recent_words,
        "weekly_challenge": {
            "challenge_id": challenge.get("challenge_id"),
            "title": challenge.get("title"),
            "week_key": challenge.get("week_key"),
            "entry": {
                **({k: v for k, v in (challenge_entry or {}).items()} if challenge_entry else {}),
                "rank": challenge_rank,
                "tier": challenge_tier.get("tier"),
                "tier_label": challenge_tier.get("label"),
                "perks_unlocked": challenge_tier.get("perks_unlocked"),
            },
        },
        "summary": {
            "saved_words_count": len(saved_words),
            "recent_words_count": len(recent_words),
            "challenge_points": challenge_points,
        },
        "generated_at": _now_iso(),
    }

    if format == "payload":
        return payload

    filename_stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if format == "json":
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="lexicon-intelligence-export-{filename_stamp}.json"'},
        )

    csv_content = _export_payload_to_csv(payload)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="lexicon-intelligence-export-{filename_stamp}.csv"'},
    )


@router.get("/bootstrap")
async def word_forge_bootstrap(request: Request):
    await _ensure_feature_registry_entry()
    user = await require_auth(request)
    plan = _resolve_plan(user)

    daily_word = await _get_or_create_today_word(user)
    saved_words = await db.word_forge_saved.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "word_id": 1,
            "word": 1,
            "part_of_speech": 1,
            "definition": 1,
            "next_review_at": 1,
            "review_count": 1,
            "mastery_score": 1,
            "saved_at": 1,
            "updated_at": 1,
        },
    ).sort("updated_at", -1).limit(50).to_list(50)

    now_iso = _now_iso()
    review_queue = [
        row
        for row in saved_words
        if not row.get("next_review_at") or str(row.get("next_review_at")) <= now_iso
    ][:10]

    profile = await _update_profile(user.user_id, xp_delta=0)
    usage_summary = await _build_usage_summary(user.user_id)
    weekly_challenge = await _ensure_weekly_challenge()
    challenge_entry = await _get_challenge_entry(user.user_id, weekly_challenge.get("challenge_id"))
    challenge_rank = await _get_user_challenge_rank(weekly_challenge.get("challenge_id"), user.user_id)
    challenge_points = int((challenge_entry or {}).get("points") or 0)
    challenge_tier = _reward_tier_for_points(challenge_points)
    leaderboard_preview = await _get_weekly_leaderboard(weekly_challenge.get("challenge_id"), limit=8)

    return {
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": await _limits_snapshot(user),
        "daily_word": daily_word,
        "saved_words": saved_words,
        "review_queue": review_queue,
        "profile": profile,
        "usage_summary": usage_summary,
        "weekly_challenge": weekly_challenge,
        "weekly_challenge_entry": {
            **({k: v for k, v in challenge_entry.items()} if challenge_entry else {}),
            "rank": challenge_rank,
            "tier": challenge_tier.get("tier"),
            "tier_label": challenge_tier.get("label"),
            "perks_unlocked": challenge_tier.get("perks_unlocked"),
            "next_tier": challenge_tier.get("next_tier"),
        },
        "leaderboard_preview": leaderboard_preview,
        "capabilities": ENTERPRISE_CAPABILITIES,
        "business_contexts": ["meeting", "email", "sales", "leadership", "support"],
        "generated_at": _now_iso(),
    }


@router.post("/daily-word")
async def generate_daily_word(payload: DailyWordRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "generate_word")
    word = await _create_word_entry(user, domain=payload.domain, difficulty=payload.difficulty)
    await _log_usage(user.user_id, "generate_word", quota["plan"], {"word_id": word["word_id"], "domain": payload.domain})
    profile = await _update_profile(user.user_id, xp_delta=3)
    return {
        "word": word,
        "quota": {**quota, "used": quota["used"] + 1, "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1)},
        "profile": profile,
    }


@router.post("/quiz/submit")
async def submit_quiz(payload: QuizSubmitRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "quiz_attempt")

    word_doc = await db.word_forge_words.find_one(
        {"word_id": payload.word_id, "user_id": user.user_id},
        _word_projection(),
    )
    if not word_doc:
        word_doc = await db.word_forge_saved.find_one(
            {"word_id": payload.word_id, "user_id": user.user_id},
            {"_id": 0, "word_id": 1, "word": 1, "definition": 1, "quiz": 1},
        )
    if not word_doc:
        raise HTTPException(status_code=404, detail="Word not found for this account")

    answer = str(payload.answer or "").strip()
    normalized_answer = _normalize_text(answer)
    quiz = word_doc.get("quiz") or {}
    correct_answer = str(quiz.get("correct_answer") or "").strip()
    normalized_correct = _normalize_text(correct_answer)
    mode = payload.mode

    if mode == "mcq":
        is_correct = normalized_answer == normalized_correct
    elif mode == "usage":
        target_word = _normalize_text(str(word_doc.get("word") or ""))
        is_correct = len(answer) >= 18 and target_word in normalized_answer
    else:
        definition_tokens = {
            token
            for token in _normalize_text(str(word_doc.get("definition") or "")).split(" ")
            if len(token) > 3
        }
        overlap = [token for token in normalized_answer.split(" ") if token in definition_tokens]
        is_correct = len(overlap) >= 2

    score = 100 if is_correct else 62
    feedback = (
        "Excellent. Your interpretation is correct and context-ready for professional usage."
        if is_correct
        else f"Close, but not fully aligned. Correct answer: {correct_answer or str(word_doc.get('word') or 'N/A')}"
    )

    await _log_usage(
        user.user_id,
        "quiz_attempt",
        quota["plan"],
        {"word_id": payload.word_id, "mode": mode, "is_correct": bool(is_correct), "score": score},
    )
    profile = await _update_profile(user.user_id, xp_delta=10 if is_correct else 3, mastered_delta=1 if is_correct else 0)

    return {
        "word_id": payload.word_id,
        "mode": mode,
        "is_correct": bool(is_correct),
        "score": score,
        "feedback": feedback,
        "correct_answer": correct_answer,
        "explanation": str(quiz.get("explanation") or ""),
        "quota": {**quota, "used": quota["used"] + 1, "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1)},
        "profile": profile,
    }


@router.post("/saved/toggle")
async def toggle_saved_word(payload: SavedToggleRequest, request: Request):
    user = await require_auth(request)

    if not payload.save:
        deleted = await db.word_forge_saved.delete_one({"user_id": user.user_id, "word_id": payload.word_id})
        return {"status": "unsaved", "word_id": payload.word_id, "deleted": int(deleted.deleted_count)}

    quota = await _enforce_action_limit(user, "save_word")
    word_doc = await db.word_forge_words.find_one({"word_id": payload.word_id, "user_id": user.user_id}, _word_projection())
    if not word_doc:
        raise HTTPException(status_code=404, detail="Word not found")

    existing = await db.word_forge_saved.find_one(
        {"user_id": user.user_id, "word_id": payload.word_id},
        {"_id": 0, "saved_id": 1, "review_count": 1, "mastery_score": 1, "saved_at": 1},
    )
    now = _now_iso()
    next_review_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    saved_id = str(existing.get("saved_id")) if (existing and existing.get("saved_id")) else f"wf_saved_{uuid.uuid4().hex[:10]}"
    saved_doc = {
        "saved_id": saved_id,
        "user_id": user.user_id,
        "word_id": payload.word_id,
        "word": word_doc.get("word"),
        "part_of_speech": word_doc.get("part_of_speech"),
        "definition": word_doc.get("definition"),
        "next_review_at": next_review_at,
        "review_count": int(existing.get("review_count") or 0) if existing else 0,
        "mastery_score": int(existing.get("mastery_score") or 0) if existing else 0,
        "saved_at": str(existing.get("saved_at") or now) if existing else now,
        "updated_at": now,
    }
    await db.word_forge_saved.update_one(
        {"user_id": user.user_id, "word_id": payload.word_id},
        {"$set": saved_doc},
        upsert=True,
    )
    await _log_usage(user.user_id, "save_word", quota["plan"], {"word_id": payload.word_id})
    profile = await _update_profile(user.user_id, xp_delta=4, mastered_delta=0 if existing else 1)

    return {
        "status": "saved",
        "saved_word": {k: v for k, v in saved_doc.items() if k != "user_id"},
        "quota": {**quota, "used": quota["used"] + 1, "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1)},
        "profile": profile,
    }


@router.post("/review/complete")
async def complete_review(payload: ReviewCompleteRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "review_complete")

    saved = await db.word_forge_saved.find_one(
        {"user_id": user.user_id, "word_id": payload.word_id},
        {"_id": 0},
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Saved word not found")

    confidence = int(payload.confidence)
    next_days_map = {1: 1, 2: 2, 3: 3, 4: 5, 5: 7}
    mastery_gain = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}[confidence]

    next_review_at = (datetime.now(timezone.utc) + timedelta(days=next_days_map[confidence])).isoformat()
    next_mastery = min(100, int(saved.get("mastery_score") or 0) + mastery_gain)
    next_review_count = int(saved.get("review_count") or 0) + 1
    now = _now_iso()

    await db.word_forge_saved.update_one(
        {"user_id": user.user_id, "word_id": payload.word_id},
        {
            "$set": {
                "review_count": next_review_count,
                "mastery_score": next_mastery,
                "confidence_last": confidence,
                "last_reviewed_at": now,
                "next_review_at": next_review_at,
                "updated_at": now,
            }
        },
    )

    await _log_usage(
        user.user_id,
        "review_complete",
        quota["plan"],
        {"word_id": payload.word_id, "confidence": confidence, "mastery_score": next_mastery},
    )
    profile = await _update_profile(user.user_id, xp_delta=3 + confidence, mastered_delta=1 if next_mastery >= 80 else 0)

    return {
        "status": "reviewed",
        "word_id": payload.word_id,
        "confidence": confidence,
        "review_count": next_review_count,
        "mastery_score": next_mastery,
        "next_review_at": next_review_at,
        "quota": {**quota, "used": quota["used"] + 1, "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1)},
        "profile": profile,
    }


@router.post("/usage-coach")
async def usage_coach(payload: UsageCoachRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "usage_coach")

    word_doc = await db.word_forge_words.find_one({"word_id": payload.word_id, "user_id": user.user_id}, _word_projection())
    if not word_doc:
        word_doc = await db.word_forge_saved.find_one(
            {"word_id": payload.word_id, "user_id": user.user_id},
            {"_id": 0, "word_id": 1, "word": 1, "definition": 1},
        )
    if not word_doc:
        raise HTTPException(status_code=404, detail="Word not found")

    target_word = str(word_doc.get("word") or "").strip()
    prompt = f"""
Evaluate sentence usage quality for the target word.
Word: {target_word}
Definition: {word_doc.get('definition')}
Context: {payload.context_type}
Sentence: {payload.sentence}

Return strict JSON:
{{
  "clarity_score": 0-100,
  "accuracy_score": 0-100,
  "strengths": ["..."],
  "improvements": ["..."],
  "rewrite_suggestion": "single improved sentence"
}}
"""
    try:
        analysis = await generate_verified_json(
            prompt,
            "You are a professional communication coach. Return strict JSON only.",
            f"word-forge-usage-{user.user_id}-{uuid.uuid4().hex[:8]}",
        )
        if not isinstance(analysis, dict):
            raise ValueError("Invalid usage coach payload")
        clarity_score = int(max(0, min(100, int(analysis.get("clarity_score") or 0))))
        accuracy_score = int(max(0, min(100, int(analysis.get("accuracy_score") or 0))))
        strengths = [str(item).strip() for item in (analysis.get("strengths") or []) if str(item).strip()][:4]
        improvements = [str(item).strip() for item in (analysis.get("improvements") or []) if str(item).strip()][:4]
        rewrite_suggestion = str(analysis.get("rewrite_suggestion") or payload.sentence).strip()
    except Exception:
        sentence_normalized = _normalize_text(payload.sentence)
        uses_word = _normalize_text(target_word) in sentence_normalized
        clarity_score = 84 if uses_word else 55
        accuracy_score = 88 if uses_word else 48
        strengths = [
            "Sentence intent is understandable.",
            "Tone is suitable for professional communication.",
        ]
        improvements = [
            f"Use '{target_word}' more explicitly in context.",
            "Tighten sentence length for stronger impact.",
        ]
        rewrite_suggestion = (
            payload.sentence
            if uses_word
            else f"To align better, I propose a {target_word.lower()} approach that balances speed with risk control."
        )

    await _log_usage(
        user.user_id,
        "usage_coach",
        quota["plan"],
        {"word_id": payload.word_id, "context_type": payload.context_type},
    )
    profile = await _update_profile(user.user_id, xp_delta=5)

    return {
        "word_id": payload.word_id,
        "word": target_word,
        "clarity_score": clarity_score,
        "accuracy_score": accuracy_score,
        "strengths": strengths,
        "improvements": improvements,
        "rewrite_suggestion": rewrite_suggestion,
        "quota": {**quota, "used": quota["used"] + 1, "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1)},
        "profile": profile,
    }


@router.post("/business-brief")
async def business_brief(payload: BusinessBriefRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "business_brief")

    word_doc = await db.word_forge_words.find_one({"word_id": payload.word_id, "user_id": user.user_id}, _word_projection())
    if not word_doc:
        word_doc = await db.word_forge_saved.find_one(
            {"word_id": payload.word_id, "user_id": user.user_id},
            {"_id": 0, "word_id": 1, "word": 1, "definition": 1, "business_value": 1},
        )
    if not word_doc:
        raise HTTPException(status_code=404, detail="Word not found")

    word = str(word_doc.get("word") or "").strip()
    prompt = f"""
Create a practical business communication brief for the word "{word}" in context={payload.context_type}.

Return strict JSON:
{{
  "headline": "short title",
  "email_snippet": "1-2 lines",
  "meeting_talking_point": "1 line",
  "sales_pitch_line": "1 line",
  "leadership_phrase": "1 line",
  "confidence_tip": "1 line"
}}
"""
    try:
        brief = await generate_verified_json(
            prompt,
            "You are an executive communication strategist. Return strict JSON only.",
            f"word-forge-brief-{user.user_id}-{uuid.uuid4().hex[:8]}",
        )
        if not isinstance(brief, dict):
            raise ValueError("Invalid business brief payload")
    except Exception:
        brief = {
            "headline": f"{word} communication brief",
            "email_snippet": f"I recommend a {word.lower()} approach that keeps execution realistic while protecting quality.",
            "meeting_talking_point": f"Let's keep this {word.lower()} and prioritize the highest-value milestone first.",
            "sales_pitch_line": f"Our {word.lower()} strategy helps your team move faster with lower risk.",
            "leadership_phrase": f"A {word.lower()} decision balances ambition with delivery confidence.",
            "confidence_tip": f"Use {word.lower()} when presenting action-focused decisions to stakeholders.",
        }

    await _log_usage(
        user.user_id,
        "business_brief",
        quota["plan"],
        {"word_id": payload.word_id, "context_type": payload.context_type},
    )
    profile = await _update_profile(user.user_id, xp_delta=6)

    return {
        "word_id": payload.word_id,
        "word": word,
        "context_type": payload.context_type,
        "brief": {
            "headline": str(brief.get("headline") or "").strip(),
            "email_snippet": str(brief.get("email_snippet") or "").strip(),
            "meeting_talking_point": str(brief.get("meeting_talking_point") or "").strip(),
            "sales_pitch_line": str(brief.get("sales_pitch_line") or "").strip(),
            "leadership_phrase": str(brief.get("leadership_phrase") or "").strip(),
            "confidence_tip": str(brief.get("confidence_tip") or "").strip(),
        },
        "quota": {**quota, "used": quota["used"] + 1, "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1)},
        "profile": profile,
    }


@router.get("/challenge/current")
async def current_weekly_challenge(request: Request):
    user = await require_auth(request)
    challenge = await _ensure_weekly_challenge()
    entry = await _get_challenge_entry(user.user_id, challenge.get("challenge_id"))
    rank = await _get_user_challenge_rank(challenge.get("challenge_id"), user.user_id)
    limits = await _limits_snapshot(user)
    limit = int(limits.get("challenge_submit") or 0)
    used = await db.word_forge_usage_log.count_documents(
        {
            "user_id": user.user_id,
            "action": "challenge_submit",
            "created_at": {"$gte": _today_floor_iso()},
        }
    )
    quota = {
        "plan": _resolve_plan(user),
        "scope_label": _scope_label(_resolve_plan(user)),
        "used": int(used),
        "limit": int(limit),
        "remaining": -1 if int(limit) < 0 else max(0, int(limit) - int(used)),
    }
    points = int((entry or {}).get("points") or 0)
    tier_info = _reward_tier_for_points(points)
    return {
        "challenge": challenge,
        "entry": {
            **({k: v for k, v in entry.items()} if entry else {}),
            "rank": rank,
            "tier": tier_info.get("tier"),
            "tier_label": tier_info.get("label"),
            "perks_unlocked": tier_info.get("perks_unlocked"),
            "next_tier": tier_info.get("next_tier"),
        },
        "quota": quota,
        "reward_tiers": challenge.get("reward_tiers") if isinstance(challenge.get("reward_tiers"), list) else REWARD_TIERS,
        "leaderboard_preview": await _get_weekly_leaderboard(challenge.get("challenge_id"), limit=8),
        "generated_at": _now_iso(),
    }


@router.post("/challenge/submit")
async def submit_weekly_challenge(payload: ChallengeSubmitRequest, request: Request):
    user = await require_auth(request)
    quota = await _enforce_action_limit(user, "challenge_submit")
    challenge = await _ensure_weekly_challenge()

    selected_word = None
    if payload.word_id:
        selected_word = await db.word_forge_words.find_one(
            {"word_id": payload.word_id, "user_id": user.user_id},
            {"_id": 0, "word": 1, "word_id": 1},
        )
        if not selected_word:
            selected_word = await db.word_forge_saved.find_one(
                {"word_id": payload.word_id, "user_id": user.user_id},
                {"_id": 0, "word": 1, "word_id": 1},
            )

    submission_text = str(payload.submission_text or "").strip()
    token_count = max(1, len(submission_text.split()))
    base_points = 8
    depth_points = min(14, token_count // 4)
    word_bonus = 0

    if selected_word:
        selected_word_text = str(selected_word.get("word") or "").strip().lower()
        if selected_word_text and selected_word_text in submission_text.lower():
            word_bonus = 6

    points = min(30, base_points + depth_points + word_bonus)
    now = _now_iso()
    challenge_id = challenge.get("challenge_id")
    existing = await _get_challenge_entry(user.user_id, challenge_id)
    next_points_total = int(existing.get("points") or 0) + points if existing else points
    tier_info = _reward_tier_for_points(next_points_total)

    next_entry = {
        "entry_id": str(existing.get("entry_id")) if (existing and existing.get("entry_id")) else f"wf_ch_entry_{uuid.uuid4().hex[:10]}",
        "challenge_id": challenge_id,
        "user_id": user.user_id,
        "points": next_points_total,
        "submissions": int(existing.get("submissions") or 0) + 1 if existing else 1,
        "last_submission_excerpt": submission_text[:180],
        "last_submission_word": str((selected_word or {}).get("word") or ""),
        "tier": tier_info.get("tier"),
        "tier_label": tier_info.get("label"),
        "perks_unlocked": tier_info.get("perks_unlocked"),
        "updated_at": now,
        "created_at": str(existing.get("created_at") or now) if existing else now,
    }
    await db.word_forge_challenge_entries.update_one(
        {"challenge_id": challenge_id, "user_id": user.user_id},
        {"$set": next_entry},
        upsert=True,
    )

    await _log_usage(
        user.user_id,
        "challenge_submit",
        quota["plan"],
        {
            "challenge_id": challenge_id,
            "word_id": payload.word_id,
            "points_awarded": points,
        },
    )
    profile = await _update_profile(user.user_id, xp_delta=points // 2, mastered_delta=1 if points >= 18 else 0)
    rank = await _get_user_challenge_rank(challenge_id, user.user_id)
    leaderboard = await _get_weekly_leaderboard(challenge_id, limit=12)

    return {
        "status": "submitted",
        "challenge_id": challenge_id,
        "points_awarded": points,
        "entry": {
            **{k: v for k, v in next_entry.items() if k != "user_id"},
            "rank": rank,
            "next_tier": tier_info.get("next_tier"),
        },
        "profile": profile,
        "quota": {
            **quota,
            "used": quota["used"] + 1,
            "remaining": -1 if quota["limit"] < 0 else max(0, quota["remaining"] - 1),
        },
        "leaderboard": leaderboard,
    }


@router.get("/leaderboard")
async def weekly_leaderboard(request: Request):
    user = await require_auth(request)
    challenge = await _ensure_weekly_challenge()
    leaderboard = await _get_weekly_leaderboard(challenge.get("challenge_id"), limit=30)
    user_rank = await _get_user_challenge_rank(challenge.get("challenge_id"), user.user_id)
    return {
        "challenge": challenge,
        "leaderboard": leaderboard,
        "reward_tiers": challenge.get("reward_tiers") if isinstance(challenge.get("reward_tiers"), list) else REWARD_TIERS,
        "current_user": {
            "user_id": user.user_id,
            "rank": user_rank,
        },
        "generated_at": _now_iso(),
    }


@router.get("/saved")
async def list_saved_words(request: Request):
    user = await require_auth(request)
    rows = await db.word_forge_saved.find(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "word_id": 1,
            "word": 1,
            "part_of_speech": 1,
            "definition": 1,
            "next_review_at": 1,
            "review_count": 1,
            "mastery_score": 1,
            "saved_at": 1,
            "updated_at": 1,
        },
    ).sort("updated_at", -1).limit(100).to_list(100)
    return {"saved_words": rows, "count": len(rows)}


@router.get("/analytics")
async def word_forge_analytics(request: Request):
    user = await require_auth(request)
    profile = await _update_profile(user.user_id, xp_delta=0)
    usage_summary = await _build_usage_summary(user.user_id)
    saved_count = await db.word_forge_saved.count_documents({"user_id": user.user_id})
    return {
        "plan": _resolve_plan(user),
        "scope_label": _scope_label(_resolve_plan(user)),
        "profile": profile,
        "usage_summary": usage_summary,
        "saved_words": int(saved_count),
        "tracked_actions": list(ACTION_TO_ENTITLEMENT_KEY.keys()),
        "generated_at": _now_iso(),
    }
