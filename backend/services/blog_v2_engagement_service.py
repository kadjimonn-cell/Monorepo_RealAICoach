"""Read streak + smart reminder loop for Blog V2."""

from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from utils.llm_helper import generate_verified_json

BLOG_V2_POSTS = "blog_v2_posts"
MEMBER_PLANS = {"basic", "premium", "admin"}


BLOG_V2_ENGAGEMENT = "blog_v2_engagement"
BLOG_V2_WEEKLY_DIGESTS = "blog_v2_weekly_digests"
BLOG_V2_NEXT_BEST_CACHE = "blog_v2_next_best_cache"
BLOG_V2_REFERRAL_EVENTS = "blog_v2_referral_events"
BLOG_V2_PREMIUM_UNLOCKS = "blog_v2_premium_unlocks"
BLOG_V2_FUNNEL_EVENTS = "blog_v2_funnel_events"
REMINDER_MODES = {"adaptive", "daily", "three_per_week"}
MILESTONE_THRESHOLDS = [3, 7, 14, 30, 60]
REFERRAL_BOOST_DAYS = 2
FUNNEL_COOLDOWN_SECONDS = 30
FUNNEL_DEDUPE_WINDOW_SECONDS = 300
SHARE_VARIANT_KEYS = ("short", "long", "benefit")
SHARE_CHANNEL_KEYS = ("whatsapp", "x", "linkedin", "telegram", "facebook", "reddit", "email", "tiktok", "youtube", "copy")
SHARE_VARIANT_LABELS = {
    "short": "Short",
    "long": "Long",
    "benefit": "Benefit-first",
}
SHARE_OPTIMIZER_WINDOW_DAYS = 14
SHARE_OPTIMIZER_EXPLORATION_RATE = 0.18
SHARE_OPTIMIZER_WARMUP_FLOOR = 6


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _today_key() -> str:
    return _now_utc().date().isoformat()


def _week_key(dt: Optional[datetime] = None) -> str:
    current = dt or _now_utc()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _parse_date_key(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    text = text[:10]
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _parse_dt(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _normalize_read_dates(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    keep: set[str] = set()
    for row in values:
        d = _parse_date_key(row)
        if d:
            keep.add(d.isoformat())
    ordered = sorted(keep)
    return ordered[-60:]


def _is_member(viewer_plan: str) -> bool:
    return str(viewer_plan or "free").lower() in MEMBER_PLANS


def _owner_user_id(owner_id: str) -> str:
    raw = str(owner_id or "")
    if raw.startswith("auth:"):
        return raw.split(":", 1)[1]
    return raw


def _invite_code(owner_id: str) -> str:
    seed = hashlib.sha1(str(owner_id or "").encode("utf-8")).hexdigest()[:8].upper()
    return f"BLOG-{seed}"


def _frontend_base_url() -> str:
    return str(os.environ.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")


def _invite_link(invite_code: str) -> str:
    base = _frontend_base_url()
    if not base:
        return f"/blog?invite={invite_code}"
    return f"{base}/blog?invite={invite_code}"


def _normalize_badges(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    seen: List[str] = []
    for row in values:
        key = str(row or "").strip().lower()
        if key and key not in seen:
            seen.append(key)
    return seen


def _normalize_share_variant(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SHARE_VARIANT_KEYS:
        return normalized
    return ""


def _share_variant_label(variant: str) -> str:
    return SHARE_VARIANT_LABELS.get(variant, "Benefit-first")


def _share_rotation_variant(channel: str, *, salt: str = "") -> str:
    seed = hashlib.sha1(f"{channel}:{_today_key()}:{salt}".encode("utf-8")).hexdigest()
    index = int(seed[:8], 16) % len(SHARE_VARIANT_KEYS)
    return SHARE_VARIANT_KEYS[index]


def _seeded_beta_draw(*, channel: str, variant: str, shares: int, unique_owners: int, total_shares: int, weighted_engagement: float) -> float:
    alpha = 1.0 + max(weighted_engagement, 0.0)
    beta = 1.0 + max((total_shares * 1.35) - weighted_engagement, 0.0)
    seed = hashlib.sha1(
        f"{channel}:{variant}:{_today_key()}:{shares}:{unique_owners}:{total_shares}".encode("utf-8")
    ).hexdigest()
    rng = random.Random(int(seed[:12], 16))
    return round(float(rng.betavariate(alpha, beta)), 6)


def _milestone_badge_key(threshold: int) -> str:
    return f"streak_{int(threshold)}"


def _next_milestone(current_streak: int) -> Optional[Dict[str, int]]:
    for threshold in MILESTONE_THRESHOLDS:
        if current_streak < threshold:
            return {
                "threshold": threshold,
                "remaining": max(0, threshold - current_streak),
            }
    return None


def _ensure_growth_fields(doc: Dict[str, Any], owner_id: str) -> tuple[Dict[str, Any], bool]:
    changed = False
    out = dict(doc or {})

    milestones = out.get("milestones") if isinstance(out.get("milestones"), dict) else {}
    if not isinstance(milestones.get("badges"), list):
        milestones["badges"] = []
        changed = True
    if "last_unlocked_at" not in milestones:
        milestones["last_unlocked_at"] = ""
        changed = True
    out["milestones"] = milestones

    reward_wallet = out.get("reward_wallet") if isinstance(out.get("reward_wallet"), dict) else {}
    for key in ["unlock_tokens", "premium_preview_unlocks_used", "referral_bonus_days_total"]:
        if key not in reward_wallet:
            reward_wallet[key] = 0
            changed = True
    out["reward_wallet"] = reward_wallet

    referral = out.get("referral") if isinstance(out.get("referral"), dict) else {}
    code = str(referral.get("invite_code") or "").strip().upper()
    if not code:
        code = _invite_code(owner_id)
        referral["invite_code"] = code
        changed = True
    if not str(referral.get("invite_link") or "").strip():
        referral["invite_link"] = _invite_link(code)
        changed = True
    for key, default in {
        "referrals_count": 0,
        "referred_by_code": "",
        "last_claimed_at": "",
    }.items():
        if key not in referral:
            referral[key] = default
            changed = True
    out["referral"] = referral

    sequencing = out.get("sequencing") if isinstance(out.get("sequencing"), dict) else {}
    if not isinstance(sequencing.get("next_best_post_ids"), list):
        sequencing["next_best_post_ids"] = []
        changed = True
    for key in ["next_best_generated_at", "last_digest_at", "last_email_digest_at"]:
        if key not in sequencing:
            sequencing[key] = ""
            changed = True
    out["sequencing"] = sequencing

    reminder_settings = out.get("reminder_settings") if isinstance(out.get("reminder_settings"), dict) else {}
    digest = reminder_settings.get("digest") if isinstance(reminder_settings.get("digest"), dict) else {}
    if "in_app_enabled" not in digest:
        digest["in_app_enabled"] = True
        changed = True
    if "email_enabled" not in digest:
        digest["email_enabled"] = True
        changed = True
    reminder_settings["digest"] = digest
    out["reminder_settings"] = reminder_settings

    return out, changed


def _default_doc(owner_id: str) -> Dict[str, Any]:
    now = _now_iso()
    invite_code = _invite_code(owner_id)
    return {
        "owner_id": owner_id,
        "streak_current": 0,
        "streak_longest": 0,
        "last_read_date": "",
        "read_dates": [],
        "reminder_settings": {
            "enabled": True,
            "mode": "adaptive",
            "digest": {
                "in_app_enabled": True,
                "email_enabled": True,
            },
        },
        "reminder_state": {
            "next_reminder_at": now,
            "snoozed_until": "",
            "last_action": "seeded",
            "last_action_at": now,
        },
        "metrics": {
            "total_reads": 0,
            "total_read_days": 0,
        },
        "milestones": {
            "badges": [],
            "last_unlocked_at": "",
        },
        "reward_wallet": {
            "unlock_tokens": 0,
            "premium_preview_unlocks_used": 0,
            "referral_bonus_days_total": 0,
        },
        "referral": {
            "invite_code": invite_code,
            "invite_link": _invite_link(invite_code),
            "referrals_count": 0,
            "referred_by_code": "",
            "last_claimed_at": "",
        },
        "sequencing": {
            "next_best_post_ids": [],
            "next_best_generated_at": "",
            "last_digest_at": "",
            "last_email_digest_at": "",
        },
        "created_at": now,
        "updated_at": now,
    }


async def ensure_engagement_indexes(db) -> None:
    coll = db[BLOG_V2_ENGAGEMENT]
    await coll.create_index("owner_id", unique=True)
    await coll.create_index("updated_at")
    await coll.create_index("referral.invite_code")

    digest_coll = db[BLOG_V2_WEEKLY_DIGESTS]
    await digest_coll.create_index([("owner_id", 1), ("week_key", 1)], unique=True)
    await digest_coll.create_index("generated_at")

    next_best_coll = db[BLOG_V2_NEXT_BEST_CACHE]
    await next_best_coll.create_index([("owner_id", 1), ("week_key", 1)], unique=True)

    referral_events = db[BLOG_V2_REFERRAL_EVENTS]
    await referral_events.create_index("claimer_owner_id", unique=True)
    await referral_events.create_index("invite_code")

    unlock_coll = db[BLOG_V2_PREMIUM_UNLOCKS]
    await unlock_coll.create_index([("owner_id", 1), ("post_id", 1)], unique=True)
    await unlock_coll.create_index("unlocked_at")

    funnel_coll = db[BLOG_V2_FUNNEL_EVENTS]
    await funnel_coll.create_index([("owner_id", 1), ("event_name", 1), ("created_at", -1)])
    await funnel_coll.create_index([("owner_id", 1), ("event_name", 1), ("context.channel", 1), ("created_at", -1)])


async def _get_or_create_doc(db, owner_id: str) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    coll = db[BLOG_V2_ENGAGEMENT]
    defaults = _default_doc(owner_id)
    await coll.update_one(
        {"owner_id": owner_id},
        {"$setOnInsert": defaults},
        upsert=True,
    )
    doc = await coll.find_one({"owner_id": owner_id}, {"_id": 0})
    current = doc or defaults
    normalized, changed = _ensure_growth_fields(current, owner_id)
    if changed:
        normalized["updated_at"] = _now_iso()
        await coll.update_one({"owner_id": owner_id}, {"$set": normalized}, upsert=True)
    return normalized


def _adaptive_interval_days(read_dates: List[str], current_streak: int) -> int:
    today = _now_utc().date()
    seven_days_ago = today - timedelta(days=6)
    active_days = 0
    for key in read_dates:
        parsed = _parse_date_key(key)
        if parsed and parsed >= seven_days_ago:
            active_days += 1

    if active_days >= 5 or current_streak >= 7:
        return 3
    if active_days >= 3 or current_streak >= 3:
        return 2
    return 1


def _interval_days(mode: str, read_dates: List[str], current_streak: int) -> int:
    m = str(mode or "adaptive").strip().lower()
    if m == "daily":
        return 1
    if m == "three_per_week":
        return 2
    return _adaptive_interval_days(read_dates, current_streak)


def _next_reminder_iso(mode: str, read_dates: List[str], current_streak: int) -> str:
    interval = _interval_days(mode, read_dates, current_streak)
    base = _now_utc() + timedelta(days=interval)
    target = base.replace(hour=9, minute=0, second=0, microsecond=0)
    return target.isoformat()


def _days_to_keep_streak(last_read_date: str, current_streak: int) -> int:
    if current_streak <= 0:
        return 0
    parsed = _parse_date_key(last_read_date)
    if not parsed:
        return 0
    today = _now_utc().date()
    delta = (today - parsed).days
    if delta <= 0:
        return 1
    if delta == 1:
        return 0
    return 0


def _reminder_status(doc: Dict[str, Any]) -> str:
    settings = doc.get("reminder_settings") or {}
    if not bool(settings.get("enabled", True)):
        return "off"

    state = doc.get("reminder_state") or {}
    now = _now_utc()

    snoozed_until = _parse_dt(state.get("snoozed_until"))
    if snoozed_until and snoozed_until > now:
        return "snoozed"

    next_reminder = _parse_dt(state.get("next_reminder_at"))
    if not next_reminder or next_reminder <= now:
        return "due"
    return "scheduled"


def _reminder_message(status: str, current_streak: int, days_to_keep_streak: int) -> str:
    if status == "off":
        return "Reminders are off. Turn them on to protect your reading momentum."
    if status == "snoozed":
        return "Reminder snoozed for now. We'll check back at the next best moment."
    if status == "scheduled":
        return "Your next smart reminder is scheduled based on your reading pattern."

    if current_streak <= 0:
        return "Start your first reading streak today with one focused article."
    if days_to_keep_streak == 0:
        return f"Read one article today to protect your {current_streak}-day streak."
    return f"Great momentum — keep building your {current_streak}-day streak today."


async def _loop_payload(db, viewer_plan: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    current_streak = max(0, int(doc.get("streak_current") or 0))
    longest_streak = max(current_streak, int(doc.get("streak_longest") or 0))
    last_read_date = str(doc.get("last_read_date") or "")
    settings = doc.get("reminder_settings") or {}
    mode = str(settings.get("mode") or "adaptive")
    if mode not in REMINDER_MODES:
        mode = "adaptive"

    reminder_state = doc.get("reminder_state") or {}
    milestones = doc.get("milestones") if isinstance(doc.get("milestones"), dict) else {}
    badges = _normalize_badges(milestones.get("badges"))
    reward_wallet = doc.get("reward_wallet") if isinstance(doc.get("reward_wallet"), dict) else {}
    referral = doc.get("referral") if isinstance(doc.get("referral"), dict) else {}
    sequencing = doc.get("sequencing") if isinstance(doc.get("sequencing"), dict) else {}
    digest_settings = ((settings.get("digest") or {}) if isinstance(settings.get("digest"), dict) else {})
    status = _reminder_status(doc)
    days_to_keep = _days_to_keep_streak(last_read_date, current_streak)

    locked_premium_available = False
    if not _is_member(viewer_plan):
        locked_premium_available = await db[BLOG_V2_POSTS].count_documents(
            {"active": True, "premium_required": True}
        ) > 0

    show_upgrade_nudge = (not _is_member(viewer_plan)) and current_streak >= 3 and locked_premium_available

    return {
        "streak": {
            "current": current_streak,
            "longest": longest_streak,
            "last_read_date": last_read_date,
            "days_to_keep_streak": days_to_keep,
            "badges": badges,
            "next_milestone": _next_milestone(current_streak),
        },
        "reminder": {
            "enabled": bool(settings.get("enabled", True)),
            "mode": mode,
            "status": status,
            "message": _reminder_message(status, current_streak, days_to_keep),
            "next_reminder_at": str(reminder_state.get("next_reminder_at") or ""),
            "snoozed_until": str(reminder_state.get("snoozed_until") or ""),
            "recommended_action": "open_latest_article",
            "digest": {
                "in_app_enabled": bool(digest_settings.get("in_app_enabled", True)),
                "email_enabled": bool(digest_settings.get("email_enabled", True)),
                "last_digest_at": str(sequencing.get("last_digest_at") or ""),
                "last_email_digest_at": str(sequencing.get("last_email_digest_at") or ""),
            },
        },
        "conversion_trigger": {
            "show_upgrade_nudge": show_upgrade_nudge,
            "reason": "streak_threshold_met_and_premium_locked_available" if show_upgrade_nudge else "inactive",
            "streak_threshold": 3,
            "locked_premium_available": locked_premium_available,
        },
        "rewards": {
            "unlock_tokens": int(reward_wallet.get("unlock_tokens") or 0),
            "premium_preview_unlocks_used": int(reward_wallet.get("premium_preview_unlocks_used") or 0),
            "referral_bonus_days_total": int(reward_wallet.get("referral_bonus_days_total") or 0),
            "invite_code": str(referral.get("invite_code") or ""),
            "invite_link": str(referral.get("invite_link") or ""),
            "referrals_count": int(referral.get("referrals_count") or 0),
        },
    }


def build_public_engagement_preview() -> Dict[str, Any]:
    return {
        "streak": {
            "current": 0,
            "longest": 0,
            "last_read_date": "",
            "days_to_keep_streak": 0,
            "badges": [],
            "next_milestone": {"threshold": 3, "remaining": 3},
        },
        "reminder": {
            "enabled": False,
            "mode": "adaptive",
            "status": "signin_required",
            "message": "Sign in to track your reading streak and unlock smart reminders.",
            "next_reminder_at": "",
            "snoozed_until": "",
            "recommended_action": "signin",
            "digest": {
                "in_app_enabled": False,
                "email_enabled": False,
                "last_digest_at": "",
                "last_email_digest_at": "",
            },
        },
        "conversion_trigger": {
            "show_upgrade_nudge": False,
            "reason": "signin_required",
            "streak_threshold": 3,
            "locked_premium_available": True,
        },
        "rewards": {
            "unlock_tokens": 0,
            "premium_preview_unlocks_used": 0,
            "referral_bonus_days_total": 0,
            "invite_code": "",
            "invite_link": "",
            "referrals_count": 0,
        },
    }


def _apply_milestone_rewards(doc: Dict[str, Any], current_streak: int) -> Dict[str, Any]:
    milestones = doc.get("milestones") if isinstance(doc.get("milestones"), dict) else {"badges": []}
    badges = _normalize_badges(milestones.get("badges"))
    reward_wallet = doc.get("reward_wallet") if isinstance(doc.get("reward_wallet"), dict) else {}
    unlock_tokens = int(reward_wallet.get("unlock_tokens") or 0)

    newly_unlocked = []
    for threshold in MILESTONE_THRESHOLDS:
        key = _milestone_badge_key(threshold)
        if current_streak >= threshold and key not in badges:
            badges.append(key)
            newly_unlocked.append(key)

    if newly_unlocked:
        unlock_tokens += len(newly_unlocked)
        milestones["last_unlocked_at"] = _now_iso()

    milestones["badges"] = badges
    reward_wallet["unlock_tokens"] = unlock_tokens
    doc["milestones"] = milestones
    doc["reward_wallet"] = reward_wallet
    return doc


async def get_owner_engagement_loop(db, owner_id: str, viewer_plan: str) -> Dict[str, Any]:
    doc = await _get_or_create_doc(db, owner_id)
    return await _loop_payload(db, viewer_plan, doc)


async def record_owner_read_event(db, owner_id: str, viewer_plan: str) -> Dict[str, Any]:
    coll = db[BLOG_V2_ENGAGEMENT]
    doc = await _get_or_create_doc(db, owner_id)

    today = _today_key()
    last_read_date = str(doc.get("last_read_date") or "")
    last_date = _parse_date_key(last_read_date)

    read_dates = _normalize_read_dates(doc.get("read_dates"))
    current = max(0, int(doc.get("streak_current") or 0))
    longest = max(0, int(doc.get("streak_longest") or 0))

    if today not in read_dates:
        today_date = _parse_date_key(today)
        if not last_date:
            current = 1
        elif today_date and (today_date - last_date).days == 1:
            current += 1
        elif today_date and (today_date - last_date).days == 0:
            current = max(1, current)
        else:
            current = 1
        longest = max(longest, current)
        read_dates.append(today)

    read_dates = _normalize_read_dates(read_dates)

    settings = doc.get("reminder_settings") or {}
    mode = str(settings.get("mode") or "adaptive")
    if mode not in REMINDER_MODES:
        mode = "adaptive"
    digest_settings = settings.get("digest") if isinstance(settings.get("digest"), dict) else {
        "in_app_enabled": True,
        "email_enabled": True,
    }

    reminder_enabled = bool(settings.get("enabled", True))
    reminder_state = doc.get("reminder_state") or {}
    reminder_state["snoozed_until"] = ""
    reminder_state["next_reminder_at"] = _next_reminder_iso(mode, read_dates, current) if reminder_enabled else ""
    reminder_state["last_action"] = "read_event"
    reminder_state["last_action_at"] = _now_iso()

    metrics = doc.get("metrics") or {}
    total_reads = max(0, int(metrics.get("total_reads") or 0)) + 1

    patch = {
        "owner_id": owner_id,
        "streak_current": current,
        "streak_longest": longest,
        "last_read_date": today,
        "read_dates": read_dates,
        "reminder_settings": {
            "enabled": reminder_enabled,
            "mode": mode,
            "digest": {
                "in_app_enabled": bool(digest_settings.get("in_app_enabled", True)),
                "email_enabled": bool(digest_settings.get("email_enabled", True)),
            },
        },
        "reminder_state": reminder_state,
        "metrics": {
            "total_reads": total_reads,
            "total_read_days": len(read_dates),
        },
        "updated_at": _now_iso(),
    }

    patch = _apply_milestone_rewards(patch, current)

    await coll.update_one({"owner_id": owner_id}, {"$set": patch}, upsert=True)
    fresh = await coll.find_one({"owner_id": owner_id}, {"_id": 0})
    return await _loop_payload(db, viewer_plan, fresh or patch)


async def update_owner_reminder_settings(
    db,
    *,
    owner_id: str,
    viewer_plan: str,
    enabled: Optional[bool],
    mode: Optional[str],
    digest_in_app_enabled: Optional[bool] = None,
    digest_email_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    coll = db[BLOG_V2_ENGAGEMENT]
    doc = await _get_or_create_doc(db, owner_id)

    current_settings = doc.get("reminder_settings") or {}
    digest_settings = current_settings.get("digest") if isinstance(current_settings.get("digest"), dict) else {}
    next_enabled = bool(current_settings.get("enabled", True)) if enabled is None else bool(enabled)
    next_mode = str(current_settings.get("mode") or "adaptive")
    if mode is not None:
        candidate = str(mode).strip().lower()
        if candidate in REMINDER_MODES:
            next_mode = candidate

    next_digest_in_app = bool(digest_settings.get("in_app_enabled", True)) if digest_in_app_enabled is None else bool(digest_in_app_enabled)
    next_digest_email = bool(digest_settings.get("email_enabled", True)) if digest_email_enabled is None else bool(digest_email_enabled)

    read_dates = _normalize_read_dates(doc.get("read_dates"))
    current_streak = max(0, int(doc.get("streak_current") or 0))

    reminder_state = doc.get("reminder_state") or {}
    reminder_state["next_reminder_at"] = _next_reminder_iso(next_mode, read_dates, current_streak) if next_enabled else ""
    reminder_state["snoozed_until"] = ""
    reminder_state["last_action"] = "settings_updated"
    reminder_state["last_action_at"] = _now_iso()

    await coll.update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "reminder_settings": {
                    "enabled": next_enabled,
                    "mode": next_mode,
                    "digest": {
                        "in_app_enabled": next_digest_in_app,
                        "email_enabled": next_digest_email,
                    },
                },
                "reminder_state": reminder_state,
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    fresh = await coll.find_one({"owner_id": owner_id}, {"_id": 0})
    return await _loop_payload(db, viewer_plan, fresh or doc)


async def apply_owner_reminder_action(
    db,
    *,
    owner_id: str,
    viewer_plan: str,
    action: str,
) -> Dict[str, Any]:
    coll = db[BLOG_V2_ENGAGEMENT]
    doc = await _get_or_create_doc(db, owner_id)

    action_key = str(action or "").strip().lower()
    settings = doc.get("reminder_settings") or {}
    mode = str(settings.get("mode") or "adaptive")
    if mode not in REMINDER_MODES:
        mode = "adaptive"
    enabled = bool(settings.get("enabled", True))

    read_dates = _normalize_read_dates(doc.get("read_dates"))
    current_streak = max(0, int(doc.get("streak_current") or 0))
    reminder_state = doc.get("reminder_state") or {}

    now = _now_utc()
    if action_key == "snooze_24h":
        reminder_state["snoozed_until"] = (now + timedelta(hours=24)).isoformat()
        reminder_state["next_reminder_at"] = (now + timedelta(hours=24)).replace(minute=0, second=0, microsecond=0).isoformat()
    elif action_key == "dismiss":
        reminder_state["snoozed_until"] = ""
        reminder_state["next_reminder_at"] = _next_reminder_iso(mode, read_dates, current_streak) if enabled else ""
    elif action_key == "trigger_now":
        reminder_state["snoozed_until"] = ""
        reminder_state["next_reminder_at"] = now.isoformat()

    reminder_state["last_action"] = action_key or "unknown"
    reminder_state["last_action_at"] = _now_iso()

    await coll.update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "reminder_state": reminder_state,
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    fresh = await coll.find_one({"owner_id": owner_id}, {"_id": 0})
    return await _loop_payload(db, viewer_plan, fresh or doc)


async def get_owner_unlocked_post_ids(db, owner_id: str) -> set[str]:
    await ensure_engagement_indexes(db)
    rows = await db[BLOG_V2_PREMIUM_UNLOCKS].find(
        {"owner_id": owner_id}, {"_id": 0, "post_id": 1}
    ).to_list(length=1200)
    return {str(r.get("post_id")) for r in rows if r.get("post_id")}


async def consume_unlock_token_for_post(
    db,
    *,
    owner_id: str,
    post_id: str,
) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    doc = await _get_or_create_doc(db, owner_id)

    already = await db[BLOG_V2_PREMIUM_UNLOCKS].count_documents({"owner_id": owner_id, "post_id": post_id}) > 0
    reward_wallet = doc.get("reward_wallet") if isinstance(doc.get("reward_wallet"), dict) else {}
    tokens = max(0, int(reward_wallet.get("unlock_tokens") or 0))

    if already:
        return {
            "ok": True,
            "status": "already_unlocked",
            "post_id": post_id,
            "remaining_tokens": tokens,
        }

    if tokens <= 0:
        return {
            "ok": False,
            "reason": "no_unlock_tokens",
            "post_id": post_id,
            "remaining_tokens": 0,
        }

    now = _now_iso()
    reward_wallet["unlock_tokens"] = tokens - 1
    reward_wallet["premium_preview_unlocks_used"] = int(reward_wallet.get("premium_preview_unlocks_used") or 0) + 1

    await db[BLOG_V2_ENGAGEMENT].update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "reward_wallet": reward_wallet,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    await db[BLOG_V2_PREMIUM_UNLOCKS].update_one(
        {"owner_id": owner_id, "post_id": post_id},
        {
            "$set": {
                "owner_id": owner_id,
                "post_id": post_id,
                "unlocked_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    return {
        "ok": True,
        "status": "unlocked",
        "post_id": post_id,
        "remaining_tokens": max(0, int(reward_wallet.get("unlock_tokens") or 0)),
    }


async def record_funnel_event(
    db,
    *,
    owner_id: str,
    event_name: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    key = str(event_name or "").strip().lower()
    if not key:
        return {"ok": False, "reason": "event_name_required"}

    context_obj = context or {}
    channel = str(context_obj.get("channel") or "").strip().lower()
    if not channel:
        channel = "unknown"
    share_variant = _normalize_share_variant(context_obj.get("share_variant"))
    if share_variant:
        context_obj = {**context_obj, "share_variant": share_variant}

    now = _now_utc()
    now_iso = now.isoformat()
    cooldown_cutoff = (now - timedelta(seconds=FUNNEL_COOLDOWN_SECONDS)).isoformat()
    dedupe_cutoff = (now - timedelta(seconds=FUNNEL_DEDUPE_WINDOW_SECONDS)).isoformat()

    latest = await db[BLOG_V2_FUNNEL_EVENTS].find_one(
        {
            "owner_id": owner_id,
            "event_name": key,
            "context.channel": channel,
            "created_at": {"$gte": cooldown_cutoff},
        },
        {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if latest:
        return {
            "ok": True,
            "event_name": key,
            "status": "cooldown_suppressed",
            "channel": channel,
        }

    dedupe_match = await db[BLOG_V2_FUNNEL_EVENTS].find_one(
        {
            "owner_id": owner_id,
            "event_name": key,
            "context.channel": channel,
            "created_at": {"$gte": dedupe_cutoff},
            "context.share_variant": context_obj.get("share_variant"),
            "context.surface": context_obj.get("surface"),
            "context.link": context_obj.get("link"),
        },
        {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if dedupe_match:
        return {
            "ok": True,
            "event_name": key,
            "status": "dedupe_suppressed",
            "channel": channel,
        }

    payload = {
        "owner_id": owner_id,
        "event_name": key,
        "context": {
            **context_obj,
            "channel": channel,
        },
        "created_at": now_iso,
    }
    await db[BLOG_V2_FUNNEL_EVENTS].insert_one(payload)
    return {"ok": True, "event_name": key, "status": "recorded", "channel": channel}


async def get_funnel_summary(db, owner_id: str, *, max_rows: int = 2000) -> Dict[str, int]:
    await ensure_engagement_indexes(db)
    rows = await db[BLOG_V2_FUNNEL_EVENTS].find(
        {"owner_id": owner_id}, {"_id": 0, "event_name": 1}
    ).sort("created_at", -1).limit(max_rows).to_list(length=max_rows)

    out: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("event_name") or "").strip().lower()
        if not key:
            continue
        out[key] = out.get(key, 0) + 1
    return out


async def get_channel_attribution_summary(db, owner_id: str, *, days: int = 7) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    days = max(1, min(30, int(days or 7)))
    cutoff = (_now_utc() - timedelta(days=days)).isoformat()
    rows = await db[BLOG_V2_FUNNEL_EVENTS].find(
        {
            "owner_id": owner_id,
            "created_at": {"$gte": cutoff},
            "event_name": {"$in": ["share_clicked", "copy_clicked", "claim_success"]},
        },
        {"_id": 0, "event_name": 1, "context": 1, "created_at": 1},
    ).to_list(length=3000)

    channels: Dict[str, Dict[str, int]] = {}
    unique_click_keys: Dict[str, set[str]] = {}
    trend: Dict[str, int] = {}

    for row in rows:
        event_name = str(row.get("event_name") or "").strip().lower()
        context = row.get("context") if isinstance(row.get("context"), dict) else {}
        channel = str(context.get("channel") or "unknown").strip().lower() or "unknown"
        created_at = str(row.get("created_at") or "")
        day_key = created_at[:10] if len(created_at) >= 10 else _today_key()

        bucket = channels.setdefault(channel, {
            "clicks": 0,
            "unique_clicks": 0,
            "claim_attributed_clicks": 0,
        })

        if event_name in {"share_clicked", "copy_clicked"}:
            bucket["clicks"] += 1
            unique_set = unique_click_keys.setdefault(channel, set())
            unique_fingerprint = json.dumps(
                {
                    "link": context.get("link"),
                    "variant": context.get("share_variant"),
                    "surface": context.get("surface"),
                    "day": day_key,
                },
                sort_keys=True,
            )
            if unique_fingerprint not in unique_set:
                unique_set.add(unique_fingerprint)
                bucket["unique_clicks"] += 1

            trend[day_key] = trend.get(day_key, 0) + 1

        if event_name == "claim_success":
            bucket["claim_attributed_clicks"] += 1

    top_channel = "none"
    top_clicks = -1
    for channel, stats in channels.items():
        clicks = int(stats.get("clicks") or 0)
        if clicks > top_clicks:
            top_clicks = clicks
            top_channel = channel

    trend_rows = [
        {"date": key, "clicks": int(trend[key])}
        for key in sorted(trend.keys())
    ]

    return {
        "window_days": days,
        "channels": channels,
        "top_channel": top_channel,
        "totals": {
            "clicks": sum(int(v.get("clicks") or 0) for v in channels.values()),
            "unique_clicks": sum(int(v.get("unique_clicks") or 0) for v in channels.values()),
            "claim_attributed_clicks": sum(int(v.get("claim_attributed_clicks") or 0) for v in channels.values()),
        },
        "trend": trend_rows,
    }


async def get_share_variant_optimizer_summary(db, *, days: int = SHARE_OPTIMIZER_WINDOW_DAYS) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    days = max(7, min(30, int(days or SHARE_OPTIMIZER_WINDOW_DAYS)))
    cutoff = (_now_utc() - timedelta(days=days)).isoformat()
    rows = await db[BLOG_V2_FUNNEL_EVENTS].find(
        {
            "created_at": {"$gte": cutoff},
            "event_name": {"$in": ["share_clicked", "copy_clicked"]},
            "context.channel": {"$in": list(SHARE_CHANNEL_KEYS)},
        },
        {"_id": 0, "owner_id": 1, "context": 1},
    ).to_list(length=6000)

    channel_rows: Dict[str, Dict[str, Any]] = {}
    global_variant_shares = {variant: 0 for variant in SHARE_VARIANT_KEYS}

    for row in rows:
        context = row.get("context") if isinstance(row.get("context"), dict) else {}
        channel = str(context.get("channel") or "").strip().lower()
        variant = _normalize_share_variant(context.get("share_variant"))
        if channel not in SHARE_CHANNEL_KEYS or not variant:
            continue

        channel_bucket = channel_rows.setdefault(
            channel,
            {
                "variant_rows": {
                    key: {"shares": 0, "owner_ids": set(), "surfaces": set()}
                    for key in SHARE_VARIANT_KEYS
                },
                "sample_size": 0,
            },
        )
        variant_bucket = channel_bucket["variant_rows"][variant]
        variant_bucket["shares"] += 1
        owner_id = str(row.get("owner_id") or "")
        if owner_id:
            variant_bucket["owner_ids"].add(owner_id)
        surface = str(context.get("surface") or "unknown").strip().lower() or "unknown"
        variant_bucket["surfaces"].add(surface)
        channel_bucket["sample_size"] += 1
        global_variant_shares[variant] += 1

    channels: Dict[str, Any] = {}
    for channel in SHARE_CHANNEL_KEYS:
        stats = channel_rows.get(channel)
        sample_size = int((stats or {}).get("sample_size") or 0)
        variant_metrics: Dict[str, Any] = {}

        if not stats or sample_size <= 0:
            recommended_variant = _share_rotation_variant(channel, salt="cold-start")
            channels[channel] = {
                "recommended_variant": recommended_variant,
                "recommended_label": _share_variant_label(recommended_variant),
                "winner_variant": recommended_variant,
                "winner_label": _share_variant_label(recommended_variant),
                "winner_share_pct": 0.0,
                "sample_size": 0,
                "strategy": "warmup_rotation",
                "exploration_rate": SHARE_OPTIMIZER_EXPLORATION_RATE,
                "variant_metrics": {
                    variant: {
                        "shares": 0,
                        "unique_owners": 0,
                        "surface_count": 0,
                        "weighted_engagement": 0.0,
                        "share_pct": 0.0,
                        "draw": 0.0,
                    }
                    for variant in SHARE_VARIANT_KEYS
                },
            }
            continue

        scored_rows: List[Dict[str, Any]] = []
        for variant in SHARE_VARIANT_KEYS:
            row = stats["variant_rows"][variant]
            shares = int(row["shares"])
            unique_owners = len(row["owner_ids"])
            surface_count = len(row["surfaces"])
            weighted_engagement = round(shares + (unique_owners * 0.45) + (surface_count * 0.15), 3)
            draw = _seeded_beta_draw(
                channel=channel,
                variant=variant,
                shares=shares,
                unique_owners=unique_owners,
                total_shares=sample_size,
                weighted_engagement=weighted_engagement,
            )
            share_pct = round((shares / sample_size) * 100, 2) if sample_size > 0 else 0.0
            metric_row = {
                "shares": shares,
                "unique_owners": unique_owners,
                "surface_count": surface_count,
                "weighted_engagement": weighted_engagement,
                "share_pct": share_pct,
                "draw": draw,
            }
            variant_metrics[variant] = metric_row
            scored_rows.append({"variant": variant, **metric_row})

        scored_rows.sort(key=lambda row: (row["draw"], row["weighted_engagement"], row["shares"]), reverse=True)
        leader = scored_rows[0]
        runner_up = scored_rows[1] if len(scored_rows) > 1 else scored_rows[0]
        gate_seed = hashlib.sha1(f"{channel}:{_today_key()}:optimizer-gate".encode("utf-8")).hexdigest()
        gate_draw = int(gate_seed[:8], 16) / 0xFFFFFFFF

        strategy = "thompson_sampling"
        recommended_variant = leader["variant"]
        if sample_size < SHARE_OPTIMIZER_WARMUP_FLOOR:
            recommended_variant = _share_rotation_variant(channel, salt="warmup")
            strategy = "warmup_rotation"
        elif gate_draw < SHARE_OPTIMIZER_EXPLORATION_RATE:
            lowest_share = min(row["shares"] for row in scored_rows)
            exploration_pool = [row["variant"] for row in scored_rows if row["shares"] == lowest_share]
            recommended_variant = _share_rotation_variant(channel, salt="explore")
            if recommended_variant not in exploration_pool:
                recommended_variant = sorted(exploration_pool)[0]
            strategy = "exploration_rotation"

        channels[channel] = {
            "recommended_variant": recommended_variant,
            "recommended_label": _share_variant_label(recommended_variant),
            "winner_variant": leader["variant"],
            "winner_label": _share_variant_label(leader["variant"]),
            "winner_share_pct": leader["share_pct"],
            "sample_size": sample_size,
            "strategy": strategy,
            "exploration_rate": SHARE_OPTIMIZER_EXPLORATION_RATE,
            "confidence_hint": round(max(0.0, leader["draw"] - runner_up["draw"]), 4),
            "variant_metrics": variant_metrics,
        }

    global_top_variant = max(global_variant_shares.items(), key=lambda row: row[1])[0] if any(global_variant_shares.values()) else "benefit"
    return {
        "window_days": days,
        "generated_at": _now_iso(),
        "default_mode": "auto",
        "global_top_variant": global_top_variant,
        "global_top_variant_label": _share_variant_label(global_top_variant),
        "exploration_rate": SHARE_OPTIMIZER_EXPLORATION_RATE,
        "channels": channels,
    }


def _minimal_post_card(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "post_id": str(doc.get("post_id") or ""),
        "slug": str(doc.get("slug") or ""),
        "title": str(doc.get("title") or ""),
        "excerpt": str(doc.get("excerpt") or ""),
        "cover_image": str(doc.get("cover_image") or ""),
        "category": str(doc.get("category") or "General"),
        "author_name": str(doc.get("author_name") or "RealAICoach Editorial"),
        "read_time_minutes": int(doc.get("read_time_minutes") or 6),
        "premium_required": bool(doc.get("premium_required")),
    }


def _rule_score(doc: Dict[str, Any], category_hits: Dict[str, int], tag_hits: Dict[str, int]) -> int:
    score = int((doc.get("metrics") or {}).get("views") or 0) // 100
    category = str(doc.get("category") or "")
    score += int(category_hits.get(category, 0)) * 5
    for tag in doc.get("tags") or []:
        score += int(tag_hits.get(str(tag), 0)) * 2
    if bool(doc.get("premium_required")):
        score += 1
    return score


async def _rule_candidates(db, owner_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    history = await db["blog_v2_history"].find({"owner_id": owner_id}, {"_id": 0}).to_list(length=40)
    bookmarks = await db["blog_v2_bookmarks"].find({"owner_id": owner_id}, {"_id": 0}).to_list(length=40)
    seed_ids = {str(row.get("post_id")) for row in history + bookmarks if row.get("post_id")}

    posts = await db[BLOG_V2_POSTS].find({"active": True}, {"_id": 0}).limit(200).to_list(length=200)
    by_id = {str(p.get("post_id")): p for p in posts}

    category_hits: Dict[str, int] = {}
    tag_hits: Dict[str, int] = {}
    for pid in seed_ids:
        post = by_id.get(pid)
        if not post:
            continue
        category = str(post.get("category") or "")
        if category:
            category_hits[category] = category_hits.get(category, 0) + 1
        for tag in post.get("tags") or []:
            key = str(tag)
            tag_hits[key] = tag_hits.get(key, 0) + 1

    candidates = [p for p in posts if str(p.get("post_id")) not in seed_ids]
    candidates.sort(key=lambda row: _rule_score(row, category_hits, tag_hits), reverse=True)
    if not candidates:
        candidates = posts
    return candidates[: max(3, min(20, int(limit)))]


async def _hybrid_rerank(
    owner_id: str,
    candidates: List[Dict[str, Any]],
) -> tuple[List[str], Dict[str, str]]:
    if not candidates:
        return [], {}

    serialized = [
        {
            "slug": str(row.get("slug") or ""),
            "title": str(row.get("title") or ""),
            "excerpt": str(row.get("excerpt") or "")[:240],
            "category": str(row.get("category") or ""),
            "premium_required": bool(row.get("premium_required")),
        }
        for row in candidates[:12]
    ]

    try:
        llm_json = await generate_verified_json(
            prompt=(
                "Rank these blog candidates for next-best reading sequence. "
                "Return JSON with ranked_slugs array and reasoning object keyed by slug.\n"
                f"Candidates: {json.dumps(serialized, ensure_ascii=False)}"
            ),
            system_message=(
                "You are a growth editor optimizing for sustained weekly engagement and practical progression. "
                "Prefer thematic continuity and actionable depth."
            ),
            session_id=f"blog-next-best-{owner_id[:48]}-{_week_key()}",
            model="gpt-5.2",
            feature="blog_v2_next_best_rerank",
            user_id=_owner_user_id(owner_id),
        )
        ranked_slugs = [str(x).strip() for x in (llm_json.get("ranked_slugs") or []) if str(x).strip()]
        reasoning_obj = llm_json.get("reasoning") if isinstance(llm_json.get("reasoning"), dict) else {}
        reasoning = {str(k): str(v) for k, v in reasoning_obj.items()}
        if ranked_slugs:
            return ranked_slugs, reasoning
    except Exception:
        pass

    fallback = [str(row.get("slug") or "") for row in candidates if row.get("slug")]
    return fallback, {}


async def get_next_best_sequence(
    db,
    *,
    owner_id: str,
    viewer_plan: str,
    limit: int = 5,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    week = _week_key()
    limit = max(1, min(10, int(limit or 5)))

    cache_coll = db[BLOG_V2_NEXT_BEST_CACHE]
    cached = await cache_coll.find_one({"owner_id": owner_id, "week_key": week}, {"_id": 0})
    if cached and not force_refresh:
        items = cached.get("items") or []
        return {
            "week_key": week,
            "strategy": "hybrid_rules_gpt52",
            "source": "cache",
            "generated_at": cached.get("generated_at"),
            "items": items[:limit],
        }

    candidates = await _rule_candidates(db, owner_id, limit=12)
    ranked_slugs, reasoning = await _hybrid_rerank(owner_id, candidates)

    by_slug = {str(row.get("slug") or ""): row for row in candidates}
    ordered: List[Dict[str, Any]] = []
    used = set()

    for slug in ranked_slugs:
        row = by_slug.get(slug)
        if not row:
            continue
        card = _minimal_post_card(row)
        card["sequence_reason"] = reasoning.get(slug) or "Contextual continuation based on your recent reading patterns."
        ordered.append(card)
        used.add(slug)
        if len(ordered) >= limit:
            break

    if len(ordered) < limit:
        for row in candidates:
            slug = str(row.get("slug") or "")
            if not slug or slug in used:
                continue
            card = _minimal_post_card(row)
            card["sequence_reason"] = "High-signal follow-up article selected by behavior-based ranking."
            ordered.append(card)
            if len(ordered) >= limit:
                break

    generated_at = _now_iso()
    payload = {
        "owner_id": owner_id,
        "week_key": week,
        "generated_at": generated_at,
        "strategy": "hybrid_rules_gpt52",
        "items": ordered,
    }
    await cache_coll.update_one(
        {"owner_id": owner_id, "week_key": week},
        {"$set": payload, "$setOnInsert": {"created_at": generated_at}},
        upsert=True,
    )

    await db[BLOG_V2_ENGAGEMENT].update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "sequencing.next_best_post_ids": [str(item.get("post_id") or "") for item in ordered if item.get("post_id")],
                "sequencing.next_best_generated_at": generated_at,
                "updated_at": generated_at,
            }
        },
        upsert=True,
    )

    return {
        "week_key": week,
        "strategy": "hybrid_rules_gpt52",
        "source": "fresh",
        "generated_at": generated_at,
        "items": ordered,
    }


async def get_weekly_digest(
    db,
    *,
    owner_id: str,
    viewer_plan: str,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    await ensure_engagement_indexes(db)
    week = _week_key()
    digest_coll = db[BLOG_V2_WEEKLY_DIGESTS]

    existing = await digest_coll.find_one({"owner_id": owner_id, "week_key": week}, {"_id": 0})
    if existing and not force_refresh:
        return existing

    loop = await get_owner_engagement_loop(db, owner_id, viewer_plan)
    next_best = await get_next_best_sequence(db, owner_id=owner_id, viewer_plan=viewer_plan, limit=5, force_refresh=force_refresh)

    digest = {
        "owner_id": owner_id,
        "week_key": week,
        "generated_at": _now_iso(),
        "headline": "Your weekly reading momentum digest",
        "highlights": [
            f"Current streak: {loop['streak']['current']} day(s)",
            f"Longest streak: {loop['streak']['longest']} day(s)",
            f"Badges unlocked: {len(loop['streak'].get('badges') or [])}",
        ],
        "next_best": next_best,
        "email_sent_at": str(existing.get("email_sent_at") or "") if existing else "",
    }

    await digest_coll.update_one(
        {"owner_id": owner_id, "week_key": week},
        {"$set": digest, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )

    await db[BLOG_V2_ENGAGEMENT].update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "sequencing.last_digest_at": digest["generated_at"],
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    return digest


async def send_weekly_digest_email(
    db,
    *,
    owner_id: str,
    viewer_plan: str,
) -> Dict[str, Any]:
    from utils.email_service import is_email_configured, send_catalog_template

    if not is_email_configured():
        return {"ok": False, "status": "skipped", "reason": "email_not_configured"}

    user_id = _owner_user_id(owner_id)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
    if not user or not user.get("email"):
        return {"ok": False, "status": "skipped", "reason": "user_email_missing"}

    digest = await get_weekly_digest(db, owner_id=owner_id, viewer_plan=viewer_plan, force_refresh=False)
    posts = []
    for item in (digest.get("next_best") or {}).get("items", [])[:5]:
        slug = str(item.get("slug") or "")
        url = f"{_frontend_base_url()}/blog/{slug}" if _frontend_base_url() else f"/blog/{slug}"
        posts.append(
            {
                "title": item.get("title"),
                "category": item.get("category"),
                "author": item.get("author_name"),
                "read_time": f"{int(item.get('read_time_minutes') or 6)} min read",
                "url": url,
                "image": item.get("cover_image") or "",
            }
        )

    if not posts:
        return {"ok": False, "status": "skipped", "reason": "digest_empty"}

    week = str(digest.get("week_key") or _week_key())
    result = await send_catalog_template(
        recipient_email=str(user.get("email") or "").strip(),
        recipient_name=str(user.get("name") or "User"),
        template_key="newsletter_blog_digest",
        posts=posts,
        dedupe_key=f"blog_v2_weekly_digest::{owner_id}::{week}",
    )

    if result.get("success"):
        sent_at = _now_iso()
        await db[BLOG_V2_WEEKLY_DIGESTS].update_one(
            {"owner_id": owner_id, "week_key": week},
            {"$set": {"email_sent_at": sent_at}},
            upsert=True,
        )
        await db[BLOG_V2_ENGAGEMENT].update_one(
            {"owner_id": owner_id},
            {"$set": {"sequencing.last_email_digest_at": sent_at, "updated_at": sent_at}},
            upsert=True,
        )
        return {"ok": True, "status": "sent", "week_key": week}

    return {"ok": False, "status": "failed", "reason": str(result.get("error") or "send_failed")}


async def get_owner_rewards_snapshot(db, *, owner_id: str, viewer_plan: str) -> Dict[str, Any]:
    doc = await _get_or_create_doc(db, owner_id)
    loop = await _loop_payload(db, viewer_plan, doc)
    digest = await get_weekly_digest(db, owner_id=owner_id, viewer_plan=viewer_plan, force_refresh=False)
    next_best = await get_next_best_sequence(db, owner_id=owner_id, viewer_plan=viewer_plan, limit=5, force_refresh=False)
    funnel = await get_funnel_summary(db, owner_id)
    attribution = await get_channel_attribution_summary(db, owner_id, days=7)
    share_optimizer = await get_share_variant_optimizer_summary(db, days=SHARE_OPTIMIZER_WINDOW_DAYS)

    streak = loop.get("streak") or {}
    rewards = loop.get("rewards") or {}
    conversion = loop.get("conversion_trigger") or {}

    return {
        "streak": streak,
        "rewards": rewards,
        "conversion_trigger": conversion,
        "unlockables": {
            "premium_preview_tokens": int(rewards.get("unlock_tokens") or 0),
            "available": int(rewards.get("unlock_tokens") or 0) > 0,
        },
        "referral": {
            "invite_code": rewards.get("invite_code") or "",
            "invite_link": rewards.get("invite_link") or "",
            "referrals_count": int(rewards.get("referrals_count") or 0),
            "bonus_days_total": int(rewards.get("referral_bonus_days_total") or 0),
        },
        "weekly_digest": {
            "week_key": digest.get("week_key"),
            "generated_at": digest.get("generated_at"),
            "email_sent_at": digest.get("email_sent_at"),
            "headline": digest.get("headline"),
        },
        "next_best": {
            "week_key": next_best.get("week_key"),
            "generated_at": next_best.get("generated_at"),
            "strategy": next_best.get("strategy"),
            "items": next_best.get("items") or [],
        },
        "funnel": funnel,
        "channel_attribution": attribution,
        "share_variant_optimizer": share_optimizer,
    }


async def claim_referral_bonus(
    db,
    *,
    claimer_owner_id: str,
    viewer_plan: str,
    invite_code: str,
) -> Dict[str, Any]:
    code = str(invite_code or "").strip().upper()
    if not code:
        return {"ok": False, "reason": "invite_code_required"}

    coll = db[BLOG_V2_ENGAGEMENT]
    await ensure_engagement_indexes(db)
    claimer_doc = await _get_or_create_doc(db, claimer_owner_id)
    referrer_doc = await coll.find_one({"referral.invite_code": code}, {"_id": 0})

    if not referrer_doc:
        return {"ok": False, "reason": "invite_code_not_found"}

    referrer_owner_id = str(referrer_doc.get("owner_id") or "")
    if referrer_owner_id == claimer_owner_id:
        return {"ok": False, "reason": "cannot_claim_own_code"}

    claimer_referral = claimer_doc.get("referral") or {}
    if str(claimer_referral.get("referred_by_code") or ""):
        return {"ok": False, "reason": "already_claimed"}

    existing_event = await db[BLOG_V2_REFERRAL_EVENTS].find_one({"claimer_owner_id": claimer_owner_id}, {"_id": 0})
    if existing_event:
        return {"ok": False, "reason": "already_claimed"}

    now = _now_iso()

    def _boost_values(doc: Dict[str, Any]) -> Dict[str, Any]:
        current = max(0, int(doc.get("streak_current") or 0)) + REFERRAL_BOOST_DAYS
        longest = max(current, int(doc.get("streak_longest") or 0))
        reward_wallet = doc.get("reward_wallet") if isinstance(doc.get("reward_wallet"), dict) else {}
        reward_wallet["referral_bonus_days_total"] = int(reward_wallet.get("referral_bonus_days_total") or 0) + REFERRAL_BOOST_DAYS
        doc["reward_wallet"] = reward_wallet
        doc["streak_current"] = current
        doc["streak_longest"] = longest
        doc["updated_at"] = now
        return _apply_milestone_rewards(doc, current)

    boosted_referrer = _boost_values(await _get_or_create_doc(db, referrer_owner_id))
    boosted_claimer = _boost_values(claimer_doc)
    boosted_claimer_referral = boosted_claimer.get("referral") if isinstance(boosted_claimer.get("referral"), dict) else {}
    boosted_claimer_referral["referred_by_code"] = code
    boosted_claimer_referral["last_claimed_at"] = now
    boosted_claimer["referral"] = boosted_claimer_referral

    boosted_referrer_referral = boosted_referrer.get("referral") if isinstance(boosted_referrer.get("referral"), dict) else {}
    boosted_referrer_referral["referrals_count"] = int(boosted_referrer_referral.get("referrals_count") or 0) + 1
    boosted_referrer["referral"] = boosted_referrer_referral

    await coll.update_one({"owner_id": referrer_owner_id}, {"$set": boosted_referrer}, upsert=True)
    await coll.update_one({"owner_id": claimer_owner_id}, {"$set": boosted_claimer}, upsert=True)

    await db[BLOG_V2_REFERRAL_EVENTS].insert_one(
        {
            "invite_code": code,
            "referrer_owner_id": referrer_owner_id,
            "claimer_owner_id": claimer_owner_id,
            "boost_days": REFERRAL_BOOST_DAYS,
            "claimed_at": now,
        }
    )

    rewards = await get_owner_rewards_snapshot(db, owner_id=claimer_owner_id, viewer_plan=viewer_plan)
    return {
        "ok": True,
        "boost_days": REFERRAL_BOOST_DAYS,
        "reason": "claimed",
        "rewards": rewards,
    }
