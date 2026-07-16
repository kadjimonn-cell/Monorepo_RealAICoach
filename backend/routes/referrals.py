"""Referral Program — Backend routes for referral tracking, commission, and analytics."""

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from routes.db import db, require_admin, require_auth
from urllib.parse import quote as url_quote
from typing import Any
import uuid
import logging
import hashlib
import os
import hmac
from utils.pagination import iter_find_paginated
from utils.rate_limit import check_rate_limit
from services.referrals_analytics import load_user_profiles as analytics_load_user_profiles, group_rows_by
from shared.pricing_policy import get_monthly_price_map

router = APIRouter(prefix="/referrals", tags=["referrals"])
logger = logging.getLogger(__name__)

COMMISSION_RATE = 0.30  # 30% commission (base / Bronze)
DISCOUNT_RATE = 0.15  # 15% discount for referred users
MAX_EARNINGS_CAP = 1000  # $1000 cap per referrer

PLAN_PRICES = get_monthly_price_map()

REFERRALS_PAYOUTS_ENABLED = str(os.environ.get("REFERRALS_PAYOUTS_ENABLED") or "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
REFERRALS_FRAUD_AUTOSCAN_ENABLED = str(os.environ.get("REFERRALS_FRAUD_AUTOSCAN_ENABLED") or "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
_REFERRALS_INDEXES_READY = False
E2E_BYPASS_FALLBACK_VALUES = frozenset({"1", "true", "yes", "playwright", "playwright-e2e", "e2e"})


def _is_non_production_runtime() -> bool:
    env = str(
        os.environ.get("ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or os.environ.get("NODE_ENV")
        or ""
    ).strip().lower()
    return env not in {"production", "prod"}


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    xrip = request.headers.get("x-real-ip", "")
    if xrip:
        return xrip.strip()
    return request.client.host if request.client else "unknown"


def _normalize_idempotency_key(value: str | None) -> str:
    key = str(value or "").strip()
    if len(key) > 140:
        key = key[:140]
    return key


def _make_idempotency_fingerprint(user_id: str, scope: str, payload_hint: str) -> str:
    raw = f"{scope}:{user_id}:{payload_hint}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def _get_idempotency_replay(scope: str, owner_id: str, key: str) -> dict[str, Any] | None:
    if not key:
        return None
    row = await db.referral_idempotency.find_one(
        {"scope": scope, "owner_id": owner_id, "idempotency_key": key},
        {"_id": 0, "response": 1},
    )
    return (row or {}).get("response")


async def _save_idempotency_replay(scope: str, owner_id: str, key: str, response: dict[str, Any]) -> None:
    if not key:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.referral_idempotency.update_one(
        {"scope": scope, "owner_id": owner_id, "idempotency_key": key},
        {
            "$set": {
                "scope": scope,
                "owner_id": owner_id,
                "idempotency_key": key,
                "response": response,
                "updated_at": now_iso,
            },
            "$setOnInsert": {"created_at": now_iso},
        },
        upsert=True,
    )


def _assert_rate_limit(request: Request, action: str, limit: int, window_seconds: int, actor_hint: str = "") -> None:
    if _is_non_production_runtime():
        bypass_header = str(request.headers.get("x-e2e-test-bypass") or "").strip()
        configured_token = str(os.environ.get("E2E_RATE_LIMIT_BYPASS_TOKEN") or "").strip()
        if configured_token and bypass_header and hmac.compare_digest(bypass_header, configured_token):
            return
        if bypass_header.lower() in E2E_BYPASS_FALLBACK_VALUES:
            return

    ip = _client_ip(request)
    key = f"referrals:{action}:{actor_hint or 'anon'}:{ip}"
    if not check_rate_limit(key, limit, window_seconds):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please retry shortly.",
                "action": action,
                "window_seconds": window_seconds,
                "limit": limit,
            },
        )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


async def _load_user_profiles(user_ids: list[str]) -> dict[str, dict[str, Any]]:
    return await analytics_load_user_profiles(user_ids)


async def _ensure_referrals_indexes() -> None:
    global _REFERRALS_INDEXES_READY
    if _REFERRALS_INDEXES_READY:
        return
    try:
        await db.referral_events.create_index([("referred_user_id", 1), ("status", 1), ("created_at", -1)])
        await db.referral_events.create_index([("referrer_id", 1), ("created_at", -1)])
        await db.referral_click_log.create_index([("referrer_id", 1), ("clicked_at", -1)])
        await db.referral_credit_transactions.create_index([("user_id", 1), ("created_at", -1)])
        await db.referral_credit_transactions.create_index(
            [("user_id", 1), ("type", 1), ("source", 1), ("dedupe_key", 1)]
        )
        await db.referral_idempotency.create_index([("scope", 1), ("owner_id", 1), ("idempotency_key", 1)], unique=True)
        await db.referral_idempotency.create_index([("updated_at", -1)])
        _REFERRALS_INDEXES_READY = True
    except Exception as exc:
        logger.warning("referrals: index ensure failed (non-blocking): %s", exc)

# ─── Milestone Rewards ───
MILESTONES = [
    {"id": "m5", "referrals": 5, "bonus": 10.0, "label": "Rising Star", "icon": "star", "color": "#F59E0B"},
    {"id": "m10", "referrals": 10, "bonus": 25.0, "label": "Influencer", "icon": "flame", "color": "#EF4444"},
    {"id": "m25", "referrals": 25, "bonus": 50.0, "label": "Ambassador", "icon": "diamond", "color": "#8B5CF6"},
    {"id": "m50", "referrals": 50, "bonus": 100.0, "label": "Legendary Referrer", "icon": "trophy", "color": "#FFD700"},
]


async def check_and_award_milestones(user_id: str, total_signups: int):
    """Check if user has hit a new milestone and award bonus credits."""
    from utils.notification_helper import create_notification

    awarded = await db.referral_milestones.find({"user_id": user_id}, {"_id": 0, "milestone_id": 1}).to_list(50)
    awarded_ids = {a["milestone_id"] for a in awarded}

    for m in MILESTONES:
        if total_signups >= m["referrals"] and m["id"] not in awarded_ids:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.referral_milestones.insert_one(
                {
                    "user_id": user_id,
                    "milestone_id": m["id"],
                    "label": m["label"],
                    "bonus": m["bonus"],
                    "referrals_required": m["referrals"],
                    "achieved_at": now_iso,
                }
            )
            await credit_referral_earning(
                user_id,
                m["bonus"],
                source="milestone_bonus",
                dedupe_key=f"milestone_bonus:{user_id}:{m['id']}",
                details={"milestone_id": m["id"], "label": m["label"], "referrals": m["referrals"]},
            )
            await create_notification(
                user_id=user_id,
                title=f"Milestone Unlocked: {m['label']}!",
                message=f"Congrats! You reached {m['referrals']} referrals and earned a ${m['bonus']:.0f} bonus!",
                notif_type="milestone_unlocked",
                data={"milestone_id": m["id"], "bonus": m["bonus"], "label": m["label"]},
            )
            logger.info(f"Milestone {m['id']} awarded to {user_id}: +${m['bonus']}")


# ─── Tier System ───
TIERS = [
    {"id": "bronze", "name": "Bronze", "min_referrals": 1, "commission": 0.30, "color": "#CD7F32", "icon": "shield"},
    {
        "id": "silver",
        "name": "Silver",
        "min_referrals": 6,
        "commission": 0.35,
        "color": "#C0C0C0",
        "icon": "shield-half",
    },
    {
        "id": "gold",
        "name": "Gold",
        "min_referrals": 16,
        "commission": 0.40,
        "color": "#FFD700",
        "icon": "shield-checkmark",
    },
]


STARTER_TIER = {
    "id": "starter",
    "name": "Starter",
    "min_referrals": 0,
    "commission": 0.30,
    "color": "#6B7280",
    "icon": "person",
}


def _get_tier(referral_count: int) -> dict:
    tier = STARTER_TIER
    for t in TIERS:
        if referral_count >= t["min_referrals"]:
            tier = t
    return tier


def _get_next_tier(referral_count: int):
    for t in TIERS:
        if referral_count < t["min_referrals"]:
            return t
    return None


def _tier_commission(referral_count: int) -> float:
    return _get_tier(referral_count)["commission"]


def _gen_code(user_id: str) -> str:
    h = hashlib.md5(user_id.encode()).hexdigest()[:6].upper()
    return f"RAC-{h}"


# ─── Models ───


class ReferralStatsResponse(BaseModel):
    referral_code: str
    referral_link: str
    total_clicks: int = 0
    total_signups: int = 0
    active_subscribers: int = 0
    conversion_rate: float = 0
    total_earnings: float = 0
    pending_earnings: float = 0
    paid_earnings: float = 0
    monthly_earnings: float = 0
    commission_rate: float = COMMISSION_RATE
    discount_rate: float = DISCOUNT_RATE


class ReferralItem(BaseModel):
    referral_id: str
    referred_email: str
    referred_name: str = ""
    status: str  # clicked, signed_up, subscribed, churned
    plan: str = "free"
    commission_earned: float = 0
    created_at: str = ""
    converted_at: str = ""


class ApplyCodeRequest(BaseModel):
    code: str
    channel: str = "direct"
    idempotency_key: str | None = None


VALID_CHANNELS = {"twitter", "linkedin", "whatsapp", "email", "sms", "qr", "direct"}


# ─── User Endpoints ───


@router.get("/my-code")
async def get_my_referral_code(request: Request):
    user = await require_auth(request)
    uid = user.user_id
    code = _gen_code(uid)
    base_url = (
        request.headers.get("origin", "")
        or request.headers.get("referer", "").split("?")[0].rstrip("/")
        or "https://realaicoach.app"
    )

    existing = await db.referral_codes.find_one({"user_id": uid}, {"_id": 0})
    if not existing:
        await db.referral_codes.insert_one(
            {
                "user_id": uid,
                "code": code,
                "email": user.email,
                "name": user.name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "total_clicks": 0,
                "total_signups": 0,
                "active_subscribers": 0,
                "total_earnings": 0,
                "pending_earnings": 0,
                "paid_earnings": 0,
            }
        )

    return {
        "code": code,
        "referral_link": f"{base_url}?ref={code}",
        "commission_rate": COMMISSION_RATE,
        "discount_rate": DISCOUNT_RATE,
        "max_earnings": MAX_EARNINGS_CAP,
    }


@router.get("/my-stats")
async def get_my_stats(request: Request):
    user = await require_auth(request)
    uid = user.user_id
    code = _gen_code(uid)
    base_url = (
        request.headers.get("origin", "")
        or request.headers.get("referer", "").split("?")[0].rstrip("/")
        or "https://realaicoach.app"
    )

    doc = await db.referral_codes.find_one({"user_id": uid}, {"_id": 0}) or {}
    referrals = await db.referral_events.find({"referrer_id": uid}, {"_id": 0}).to_list(500)

    total_clicks = doc.get("total_clicks", 0)
    total_signups = sum(1 for r in referrals if r.get("status") in ("signed_up", "subscribed"))
    active_subs = sum(1 for r in referrals if r.get("status") == "subscribed")
    total_earnings = sum(r.get("commission_earned", 0) for r in referrals)

    # Tier calculation
    current_tier = _get_tier(total_signups)
    next_tier = _get_next_tier(total_signups)
    tier_commission = current_tier["commission"]

    # Detect tier change
    stored_tier = doc.get("current_tier", "starter")
    tier_unlocked = None
    if current_tier["id"] != stored_tier:
        tier_order = ["starter", "bronze", "silver", "gold"]
        if tier_order.index(current_tier["id"]) > tier_order.index(stored_tier):
            tier_unlocked = {
                "id": current_tier["id"],
                "name": current_tier["name"],
                "commission": current_tier["commission"],
                "color": current_tier["color"],
                "previous_tier": stored_tier,
            }

    # Recalculate monthly with tier commission
    monthly_tier = sum(
        PLAN_PRICES.get(r.get("plan", "free"), 0) * tier_commission
        for r in referrals
        if r.get("status") == "subscribed"
    )

    tier_info = {
        "id": current_tier["id"],
        "name": current_tier["name"],
        "commission": current_tier["commission"],
        "color": current_tier["color"],
        "icon": current_tier["icon"],
    }
    next_tier_info = None
    if next_tier:
        next_tier_info = {
            "id": next_tier["id"],
            "name": next_tier["name"],
            "commission": next_tier["commission"],
            "color": next_tier["color"],
            "min_referrals": next_tier["min_referrals"],
            "referrals_needed": next_tier["min_referrals"] - total_signups,
        }

    return {
        "referral_code": code,
        "referral_link": f"{base_url}?ref={code}",
        "total_clicks": total_clicks,
        "total_signups": total_signups,
        "active_subscribers": active_subs,
        "conversion_rate": round(total_signups / max(total_clicks, 1) * 100, 1),
        "total_earnings": round(total_earnings, 2),
        "pending_earnings": round(doc.get("pending_earnings", 0), 2),
        "paid_earnings": round(doc.get("paid_earnings", 0), 2),
        "monthly_earnings": round(monthly_tier, 2),
        "commission_rate": tier_commission,
        "discount_rate": DISCOUNT_RATE,
        "tier": tier_info,
        "next_tier": next_tier_info,
        "tier_unlocked": tier_unlocked,
        "all_tiers": TIERS,
    }


@router.post("/acknowledge-tier")
async def acknowledge_tier(request: Request):
    user = await require_auth(request)
    uid = user.user_id
    doc = await db.referral_codes.find_one({"user_id": uid}, {"_id": 0, "total_signups": 1})
    if not doc:
        return {"ok": True}
    tier = _get_tier(doc.get("total_signups", 0))
    await db.referral_codes.update_one({"user_id": uid}, {"$set": {"current_tier": tier["id"]}})
    return {"ok": True, "tier": tier["id"]}


@router.get("/my-referrals")
async def get_my_referrals(request: Request):
    user = await require_auth(request)
    uid = user.user_id

    referrals = await db.referral_events.find({"referrer_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(100)

    items = []
    for r in referrals:
        email = r.get("referred_email", "")
        masked = email[:2] + "***" + email[email.index("@") :] if "@" in email else email
        items.append(
            {
                "referral_id": r.get("referral_id", ""),
                "referred_email": masked,
                "referred_name": r.get("referred_name", ""),
                "status": r.get("status", "clicked"),
                "plan": r.get("plan", "free"),
                "commission_earned": round(r.get("commission_earned", 0), 2),
                "created_at": r.get("created_at", ""),
                "converted_at": r.get("converted_at", ""),
            }
        )

    return {"referrals": items, "total": len(items)}


@router.post("/track-click")
async def track_referral_click(request: Request):
    await _ensure_referrals_indexes()
    _assert_rate_limit(request, "track_click", limit=80, window_seconds=300)
    body = await request.json()
    code = body.get("code", "").strip().upper()
    channel = body.get("channel", "direct").lower()
    if channel not in VALID_CHANNELS:
        channel = "direct"
    if not code:
        raise HTTPException(400, "Referral code required")

    ref_doc = await db.referral_codes.find_one({"code": code}, {"_id": 0})
    if not ref_doc:
        raise HTTPException(404, "Invalid referral code")

    await db.referral_codes.update_one({"code": code}, {"$inc": {"total_clicks": 1}})
    await db.referral_click_log.insert_one(
        {
            "code": code,
            "referrer_id": ref_doc["user_id"],
            "channel": channel,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "ip": request.client.host if request.client else "",
        }
    )

    return {"success": True, "discount_rate": DISCOUNT_RATE}


@router.post("/apply-code")
async def apply_referral_code(request: Request, body: ApplyCodeRequest):
    await _ensure_referrals_indexes()
    user = await require_auth(request)
    uid = user.user_id
    _assert_rate_limit(request, "apply_code", limit=20, window_seconds=300, actor_hint=uid)

    idem = _normalize_idempotency_key(body.idempotency_key or request.headers.get("x-idempotency-key"))
    if not idem:
        idem = _make_idempotency_fingerprint(uid, "apply_code", body.code)

    replay = await _get_idempotency_replay("apply_code", uid, idem)
    if replay:
        return {**replay, "idempotent_replay": True}

    code = body.code.strip().upper()

    ref_doc = await db.referral_codes.find_one({"code": code}, {"_id": 0})
    if not ref_doc:
        raise HTTPException(404, "Invalid referral code")
    if ref_doc["user_id"] == uid:
        raise HTTPException(400, "Cannot refer yourself")

    existing = await db.referral_events.find_one({"referred_user_id": uid}, {"_id": 0})
    if existing:
        response = {
            "success": True,
            "already_referred": True,
            "discount": DISCOUNT_RATE,
            "message": f"You already have an active referral. {int(DISCOUNT_RATE * 100)}% discount remains applied.",
        }
        await _save_idempotency_replay("apply_code", uid, idem, response)
        return response

    referral_id = f"ref_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    channel = body.channel.lower() if body.channel else "direct"
    if channel not in VALID_CHANNELS:
        channel = "direct"

    await db.referral_events.insert_one(
        {
            "referral_id": referral_id,
            "referrer_id": ref_doc["user_id"],
            "referrer_code": code,
            "referred_user_id": uid,
            "referred_email": user.email,
            "referred_name": user.name,
            "status": "signed_up",
            "plan": user.subscription_plan,
            "commission_earned": 0,
            "channel": channel,
            "created_at": now,
            "converted_at": "",
            "apply_code_idempotency_key": idem,
        }
    )

    await db.referral_codes.update_one({"code": code}, {"$inc": {"total_signups": 1}})

    await db.users.update_one(
        {"user_id": uid},
        {"$set": {"referred_by": ref_doc["user_id"], "referral_code_used": code, "referral_discount": DISCOUNT_RATE}},
    )

    # Notify the referrer
    from utils.notification_helper import create_notification

    referrer_name = user.name or user.email.split("@")[0]
    await create_notification(
        user_id=ref_doc["user_id"],
        title="New Referral Signup!",
        message=f"{referrer_name} just signed up using your referral link!",
        notif_type="referral_signup",
        data={"referral_id": referral_id, "referred_name": referrer_name},
    )

    # Check milestones after signup
    updated_code = await db.referral_codes.find_one({"code": code}, {"_id": 0, "total_signups": 1})
    new_signups = (updated_code or {}).get("total_signups", 0)
    await check_and_award_milestones(ref_doc["user_id"], new_signups)

    # Check active challenges after signup
    await check_and_update_challenges(ref_doc["user_id"], now)

    response = {"success": True, "discount": DISCOUNT_RATE, "message": f"You got {int(DISCOUNT_RATE * 100)}% off!"}
    await _save_idempotency_replay("apply_code", uid, idem, response)
    return response


# ─── Public Referral Leaderboard ───


@router.get("/public-leaderboard")
async def get_public_leaderboard(request: Request):
    """Public leaderboard showing anonymized top referrers with tier badges."""
    user = None
    try:
        user = await require_auth(request)
    except Exception:
        pass

    codes = (
        await db.referral_codes.find(
            {"total_signups": {"$gt": 0}},
            {"_id": 0, "user_id": 1, "code": 1, "total_signups": 1, "total_clicks": 1, "name": 1},
        )
        .sort("total_signups", -1)
        .to_list(50)
    )

    # Enrich with referral events and user names
    leaderboard = []
    for i, c in enumerate(codes):
        events = await db.referral_events.find(
            {"referrer_code": c["code"], "status": "subscribed"}, {"_id": 0, "commission_earned": 1}
        ).to_list(500)
        earnings = sum(e.get("commission_earned", 0) for e in events)
        active_subs = len(events)
        signups = c.get("total_signups", 0)
        tier = _get_tier(signups)

        # Get user name for display (anonymize if not self)
        u = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0, "name": 1})
        full_name = (u or {}).get("name", "Anonymous")
        is_self = user and user.user_id == c["user_id"]
        display_name = full_name if is_self else _anonymize(full_name)

        leaderboard.append(
            {
                "rank": i + 1,
                "display_name": display_name,
                "is_self": bool(is_self),
                "total_signups": signups,
                "active_subscribers": active_subs,
                "total_clicks": c.get("total_clicks", 0),
                "total_earnings": round(earnings, 2),
                "tier": {
                    "id": tier["id"],
                    "name": tier["name"],
                    "color": tier["color"],
                    "commission": tier["commission"],
                },
            }
        )

    # Get current user's position if not in top 50
    my_position = None
    if user:
        my_code = await db.referral_codes.find_one({"user_id": user.user_id}, {"_id": 0, "total_signups": 1, "code": 1})
        if my_code:
            my_signups = my_code.get("total_signups", 0)
            higher = await db.referral_codes.count_documents({"total_signups": {"$gt": my_signups}})
            my_tier = _get_tier(my_signups)
            my_position = {
                "rank": higher + 1,
                "total_signups": my_signups,
                "tier": {"id": my_tier["id"], "name": my_tier["name"], "color": my_tier["color"]},
                "in_top_50": any(e.get("is_self") for e in leaderboard),
            }

    return {
        "leaderboard": leaderboard,
        "total_participants": await db.referral_codes.count_documents({}),
        "my_position": my_position,
        "tiers": TIERS,
    }


def _anonymize(name: str) -> str:
    """Turn 'John Smith' into 'J***n S.'"""
    parts = name.strip().split()
    if not parts:
        return "Anonymous"
    first = parts[0]
    if len(first) <= 2:
        masked_first = first[0] + "***"
    else:
        masked_first = first[0] + "***" + first[-1]
    if len(parts) > 1:
        return f"{masked_first} {parts[-1][0]}."
    return masked_first


# ─── Subscription Event Tracking ───


class SubscriptionEventBody(BaseModel):
    referred_user_id: str
    plan: str  # "basic" or "premium"
    idempotency_key: str | None = None


@router.post("/track-subscription")
async def track_referral_subscription(request: Request, body: SubscriptionEventBody):
    """Called when a referred user subscribes. Updates referral event and notifies referrer."""
    from utils.notification_helper import create_notification

    await _ensure_referrals_indexes()
    _assert_rate_limit(request, "track_subscription", limit=30, window_seconds=60)
    if not REFERRALS_PAYOUTS_ENABLED:
        return {
            "success": False,
            "message": "Referral payouts are temporarily disabled by platform policy.",
            "error_code": "referral_payouts_disabled",
        }

    idem = _normalize_idempotency_key(body.idempotency_key or request.headers.get("x-idempotency-key"))
    if not idem:
        idem = _make_idempotency_fingerprint(
            user_id=body.referred_user_id,
            scope="track_subscription",
            payload_hint=body.plan,
        )

    replay = await _get_idempotency_replay("track_subscription", body.referred_user_id, idem)
    if replay:
        return {**replay, "idempotent_replay": True}

    already_subscribed = await db.referral_events.find_one(
        {"referred_user_id": body.referred_user_id, "status": "subscribed"},
        {"_id": 0, "commission_earned": 1, "referral_id": 1, "referrer_id": 1},
    )
    if already_subscribed:
        response = {
            "success": True,
            "already_processed": True,
            "commission": round(float(already_subscribed.get("commission_earned") or 0), 2),
            "referral_id": str(already_subscribed.get("referral_id") or ""),
            "referrer_id": str(already_subscribed.get("referrer_id") or ""),
        }
        await _save_idempotency_replay("track_subscription", body.referred_user_id, idem, response)
        return response

    event = await db.referral_events.find_one(
        {"referred_user_id": body.referred_user_id, "status": "signed_up"}, {"_id": 0}
    )
    if not event:
        response = {"success": False, "message": "No pending referral event"}
        await _save_idempotency_replay("track_subscription", body.referred_user_id, idem, response)
        return response

    referrer_id = event["referrer_id"]
    ref_doc = await db.referral_codes.find_one({"user_id": referrer_id}, {"_id": 0, "total_signups": 1})
    signups = (ref_doc or {}).get("total_signups", 0)
    tier = _get_tier(signups)
    commission = PLAN_PRICES.get(body.plan, 0) * tier["commission"]

    mutation = await db.referral_events.update_one(
        {"referral_id": event["referral_id"], "status": "signed_up"},
        {
            "$set": {
                "status": "subscribed",
                "plan": body.plan,
                "commission_earned": round(commission, 2),
                "converted_at": datetime.now(timezone.utc).isoformat(),
                "subscription_idempotency_key": idem,
            }
        },
    )

    if mutation.modified_count == 0:
        already = await db.referral_events.find_one(
            {"referral_id": event["referral_id"], "status": "subscribed"},
            {"_id": 0, "commission_earned": 1},
        )
        response = {
            "success": True,
            "already_processed": True,
            "commission": round(float((already or {}).get("commission_earned") or 0), 2),
            "tier": _get_tier(signups)["name"],
        }
        await _save_idempotency_replay("track_subscription", body.referred_user_id, idem, response)
        return response

    # Get referred user name
    ref_user = await db.users.find_one({"user_id": body.referred_user_id}, {"_id": 0, "name": 1, "email": 1})
    referred_name = (ref_user or {}).get("name", "Someone")

    await create_notification(
        user_id=referrer_id,
        title="Cha-ching! New Subscription!",
        message=f"{referred_name} just subscribed to {body.plan.title()} Plan! ${commission:.2f}/mo added to your renewal credits.",
        notif_type="referral_subscription",
        data={
            "referral_id": event["referral_id"],
            "plan": body.plan,
            "commission": round(commission, 2),
            "referred_name": referred_name,
        },
    )

    # Credit the referrer's wallet
    await credit_referral_earning(
        referrer_id,
        commission,
        source="referral_subscription",
        dedupe_key=f"referral_subscription:{event['referral_id']}",
        details={"referred_user": body.referred_user_id, "plan": body.plan, "referred_name": referred_name},
    )

    response = {"success": True, "commission": round(commission, 2), "tier": tier["name"]}
    await _save_idempotency_replay("track_subscription", body.referred_user_id, idem, response)
    return response


# ─── Admin Endpoints ───


@router.get("/admin/analytics")
async def admin_referral_analytics(request: Request):
    await require_admin(request)
    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    total_referrers = await db.referral_codes.count_documents({})
    total_events = await db.referral_events.count_documents({})
    active_subs = await db.referral_events.count_documents({"status": "subscribed"})
    signups = await db.referral_events.count_documents({"status": {"$in": ["signed_up", "subscribed"]}})
    total_clicks = 0
    async for doc in db.referral_codes.find({}, {"_id": 0, "total_clicks": 1}):
        total_clicks += doc.get("total_clicks", 0)

    total_commission = 0.0
    monthly_revenue = 0.0
    recent_signups = 0
    week_signups = 0
    plan_dist = {}
    status_dist = {}

    # Daily trend (last 30 days)
    daily_data = {}
    for i in range(30):
        day = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        daily_data[day] = {"signups": 0, "clicks": 0, "conversions": 0}

    async for e in iter_find_paginated(
        db.referral_events,
        {},
        {"_id": 0},
        max_docs=5000,
    ):
        total_commission += e.get("commission_earned", 0)
        if e.get("status") == "subscribed":
            monthly_revenue += PLAN_PRICES.get(e.get("plan", "free"), 0) * COMMISSION_RATE

        created_at = e.get("created_at", "")
        if created_at >= thirty_days_ago and e.get("status") in ("signed_up", "subscribed"):
            recent_signups += 1
        if created_at >= seven_days_ago and e.get("status") in ("signed_up", "subscribed"):
            week_signups += 1

        day = created_at[:10]
        if day in daily_data:
            daily_data[day]["signups"] += 1
            if e.get("status") == "subscribed":
                daily_data[day]["conversions"] += 1

        plan = e.get("plan", "free")
        plan_dist[plan] = plan_dist.get(plan, 0) + 1

        status = e.get("status", "unknown")
        status_dist[status] = status_dist.get(status, 0) + 1

    async for c in iter_find_paginated(
        db.referral_click_log,
        {"clicked_at": {"$gte": thirty_days_ago}},
        {"_id": 0, "clicked_at": 1},
        max_docs=10000,
    ):
        day = c.get("clicked_at", "")[:10]
        if day in daily_data:
            daily_data[day]["clicks"] += 1

    trend = [{"date": k, **v} for k, v in daily_data.items()]

    # Tier distribution — count referrers per tier
    tier_dist = {"starter": 0, "bronze": 0, "silver": 0, "gold": 0}
    async for c in iter_find_paginated(
        db.referral_codes,
        {},
        {"_id": 0, "total_signups": 1},
        max_docs=10000,
    ):
        t = _get_tier(c.get("total_signups", 0))
        tier_dist[t["id"]] = tier_dist.get(t["id"], 0) + 1

    return {
        "total_referrers": total_referrers,
        "total_clicks": total_clicks,
        "total_signups": signups,
        "total_events": total_events,
        "active_subscribers": active_subs,
        "conversion_rate": round(signups / max(total_clicks, 1) * 100, 1),
        "total_commission_paid": round(total_commission, 2),
        "monthly_recurring_commission": round(monthly_revenue, 2),
        "recent_30d_signups": recent_signups,
        "recent_7d_signups": week_signups,
        "commission_rate": COMMISSION_RATE,
        "discount_rate": DISCOUNT_RATE,
        "trend": trend,
        "plan_distribution": plan_dist,
        "status_distribution": status_dist,
        "tier_distribution": tier_dist,
        "tiers": TIERS,
    }


@router.get("/admin/enhanced-analytics")
async def admin_enhanced_analytics(request: Request):
    """Enhanced referral analytics: detailed conversion funnel + cohort analysis."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    channel_click_totals = {ch_key: 0 for ch_key in CHANNEL_META}
    channel_event_totals = {ch_key: {"signups": 0, "subscriptions": 0, "revenue": 0.0} for ch_key in CHANNEL_META}
    total_clicks = 0
    async for click in iter_find_paginated(db.referral_click_log, {}, {"_id": 0, "channel": 1}):
        total_clicks += 1
        ch_key = click.get("channel", "direct")
        channel_click_totals[ch_key] = channel_click_totals.get(ch_key, 0) + 1

    total_signups = 0
    total_subscribed = 0
    signup_to_sub_times = []
    plan_conversions = {"free": 0, "basic": 0, "premium": 0}
    cohorts = {}

    async for e in iter_find_paginated(
        db.referral_events,
        {},
        {"_id": 0},
        max_docs=10000,
    ):
        status = e.get("status")
        if status in ("signed_up", "subscribed"):
            total_signups += 1
        if status == "subscribed":
            total_subscribed += 1
            plan = e.get("plan", "free")
            plan_conversions[plan] = plan_conversions.get(plan, 0) + 1

        ch_key = e.get("channel", "direct")
        if ch_key in channel_event_totals:
            channel_event_totals[ch_key]["signups"] += 1
            if status == "subscribed":
                channel_event_totals[ch_key]["subscriptions"] += 1
                channel_event_totals[ch_key]["revenue"] += e.get("commission_earned", 0)

        if status == "subscribed" and e.get("created_at") and e.get("converted_at"):
            try:
                t1 = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(e["converted_at"].replace("Z", "+00:00"))
                diff_hours = (t2 - t1).total_seconds() / 3600
                if diff_hours >= 0:
                    signup_to_sub_times.append(diff_hours)
            except Exception:
                pass

        created = e.get("created_at", "")
        if not created or len(created) < 7:
            continue
        month_key = created[:7]  # "YYYY-MM"
        if month_key not in cohorts:
            cohorts[month_key] = {
                "month": month_key,
                "total_signups": 0,
                "subscribed": 0,
                "churned": 0,
                "still_signed_up": 0,
                "total_revenue": 0.0,
                "avg_commission": 0.0,
                "plans": {"free": 0, "basic": 0, "premium": 0},
                "channels": {},
            }
        c = cohorts[month_key]
        c["total_signups"] += 1
        if status == "subscribed":
            c["subscribed"] += 1
            c["total_revenue"] += e.get("commission_earned", 0)
            plan = e.get("plan", "free")
            c["plans"][plan] = c["plans"].get(plan, 0) + 1
        elif status == "churned":
            c["churned"] += 1
        else:
            c["still_signed_up"] += 1

        ch = e.get("channel", "direct")
        c["channels"][ch] = c["channels"].get(ch, 0) + 1

    # --- Detailed Conversion Funnel ---
    click_to_signup_rate = round(total_signups / max(total_clicks, 1) * 100, 1)
    signup_to_sub_rate = round(total_subscribed / max(total_signups, 1) * 100, 1)
    click_to_sub_rate = round(total_subscribed / max(total_clicks, 1) * 100, 1)

    click_to_signup_drop = round(100 - click_to_signup_rate, 1)
    signup_to_sub_drop = round(100 - signup_to_sub_rate, 1)

    avg_time_to_convert_hours = round(sum(signup_to_sub_times) / max(len(signup_to_sub_times), 1), 1)
    median_time_hours = (
        round(sorted(signup_to_sub_times)[len(signup_to_sub_times) // 2], 1) if signup_to_sub_times else 0
    )

    conversion_funnel = {
        "stages": [
            {"label": "Link Clicks", "value": total_clicks, "rate": 100, "icon": "link"},
            {"label": "Signups", "value": total_signups, "rate": click_to_signup_rate, "icon": "person-add"},
            {"label": "Subscriptions", "value": total_subscribed, "rate": click_to_sub_rate, "icon": "card"},
        ],
        "drop_offs": [
            {"from": "Clicks", "to": "Signups", "drop_pct": click_to_signup_drop, "lost": total_clicks - total_signups},
            {
                "from": "Signups",
                "to": "Subscriptions",
                "drop_pct": signup_to_sub_drop,
                "lost": total_signups - total_subscribed,
            },
        ],
        "rates": {
            "click_to_signup": click_to_signup_rate,
            "signup_to_subscription": signup_to_sub_rate,
            "overall": click_to_sub_rate,
        },
        "time_to_convert": {
            "avg_hours": avg_time_to_convert_hours,
            "median_hours": median_time_hours,
            "sample_size": len(signup_to_sub_times),
        },
        "plan_conversions": plan_conversions,
    }

    # Finalize cohort stats
    cohort_list = []
    for month_key in sorted(cohorts.keys()):
        c = cohorts[month_key]
        c["conversion_rate"] = round(c["subscribed"] / max(c["total_signups"], 1) * 100, 1)
        c["churn_rate"] = round(c["churned"] / max(c["total_signups"], 1) * 100, 1)
        c["avg_commission"] = round(c["total_revenue"] / max(c["subscribed"], 1), 2)
        c["total_revenue"] = round(c["total_revenue"], 2)
        # Top channel for this cohort
        top_ch = max(c["channels"], key=c["channels"].get) if c["channels"] else "direct"
        c["top_channel"] = top_ch
        cohort_list.append(c)

    # --- Channel-wise conversion rates ---
    channel_funnels = {}
    for ch_key in CHANNEL_META:
        ch_clicks = channel_click_totals.get(ch_key, 0)
        ch_signups = channel_event_totals[ch_key]["signups"]
        ch_subs = channel_event_totals[ch_key]["subscriptions"]
        ch_revenue = channel_event_totals[ch_key]["revenue"]
        channel_funnels[ch_key] = {
            "channel": ch_key,
            "label": CHANNEL_META[ch_key]["label"],
            "color": CHANNEL_META[ch_key]["color"],
            "clicks": ch_clicks,
            "signups": ch_signups,
            "subscriptions": ch_subs,
            "revenue": round(ch_revenue, 2),
            "click_to_signup": round(ch_signups / max(ch_clicks, 1) * 100, 1),
            "signup_to_sub": round(ch_subs / max(ch_signups, 1) * 100, 1),
            "overall_rate": round(ch_subs / max(ch_clicks, 1) * 100, 1),
        }

    return {
        "conversion_funnel": conversion_funnel,
        "cohorts": cohort_list,
        "channel_funnels": list(channel_funnels.values()),
        "generated_at": now.isoformat(),
    }


@router.get("/admin/top-referrers")
async def admin_top_referrers(request: Request):
    await require_admin(request)

    codes = await db.referral_codes.find({}, {"_id": 0}).sort("total_signups", -1).to_list(50)
    referrer_ids = [str(c.get("user_id") or "") for c in codes if c.get("user_id")]
    event_rows = await db.referral_events.find(
        {"referrer_id": {"$in": referrer_ids}},
        {
            "_id": 0,
            "referrer_id": 1,
            "status": 1,
            "commission_earned": 1,
            "plan": 1,
        },
    ).to_list(5000)

    events_by_referrer = group_rows_by(event_rows, "referrer_id")

    referrers = []
    for c in codes:
        events = events_by_referrer.get(str(c.get("user_id") or ""), [])
        active = sum(1 for e in events if e.get("status") == "subscribed")
        earnings = sum(e.get("commission_earned", 0) for e in events)
        monthly = sum(
            PLAN_PRICES.get(e.get("plan", "free"), 0) * COMMISSION_RATE
            for e in events
            if e.get("status") == "subscribed"
        )
        signups_count = c.get("total_signups", 0)
        tier = _get_tier(signups_count)
        referrers.append(
            {
                "user_id": c["user_id"],
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "code": c["code"],
                "total_clicks": c.get("total_clicks", 0),
                "total_signups": signups_count,
                "active_subscribers": active,
                "total_earnings": round(earnings, 2),
                "monthly_earnings": round(monthly, 2),
                "created_at": c.get("created_at", ""),
                "tier": {
                    "id": tier["id"],
                    "name": tier["name"],
                    "color": tier["color"],
                    "commission": tier["commission"],
                },
            }
        )

    return {"referrers": referrers, "total": len(referrers)}


@router.post("/admin/seed-demo")
# ─── Admin: Email Digest Stats & Test Send ───

@router.get("/admin/email-digest-stats")
async def admin_email_digest_stats(request: Request):
    """Email digest stats for admin console."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    total_sent = await db.referral_email_sends.count_documents({})
    sent_7d = await db.referral_email_sends.count_documents({"sent_at": {"$gte": seven_days_ago}})
    sent_30d = await db.referral_email_sends.count_documents({"sent_at": {"$gte": thirty_days_ago}})
    total_users = await db.users.count_documents({"email": {"$exists": True, "$ne": ""}})

    # Tier breakdown of recipients
    pipeline = [
        {"$group": {"_id": "$tier", "count": {"$sum": 1}}},
    ]
    tier_agg = await db.referral_email_sends.aggregate(pipeline).to_list(10)
    tier_breakdown = {r["_id"]: r["count"] for r in tier_agg if r["_id"]}

    # Recent sends (last 10)
    recent = (
        await db.referral_email_sends.find(
            {}, {"_id": 0, "email": 1, "tier": 1, "rank": 1, "total_refs": 1, "sent_at": 1}
        )
        .sort("sent_at", -1)
        .to_list(10)
    )

    # Last send time
    last_send = await db.referral_email_sends.find_one({}, {"_id": 0, "sent_at": 1}, sort=[("sent_at", -1)])

    return {
        "total_sent": total_sent,
        "sent_7d": sent_7d,
        "sent_30d": sent_30d,
        "total_eligible_users": total_users,
        "tier_breakdown": tier_breakdown,
        "recent_sends": recent,
        "last_send_at": last_send.get("sent_at") if last_send else None,
        "schedule": "Every Monday at 10:00 AM UTC",
    }


@router.post("/admin/send-test-digest")
async def admin_send_test_digest(request: Request):
    """Send a test digest email to the admin."""
    user = await require_admin(request)
    # For test, we'll just trigger the full job (it'll send to all users)
    # Instead, let's generate a single email for the admin
    from utils.email_templates import _wrap
    from utils.email_service import send_email, is_email_configured

    uid = user.user_id
    name = user.name or "Admin"
    email = user.email

    ref_doc = await db.referral_codes.find_one({"user_id": uid}, {"_id": 0})
    total_refs = ref_doc.get("total_signups", 0) if ref_doc else 0
    events = await db.referral_events.find({"referrer_id": uid}, {"_id": 0}).to_list(500)
    total_earnings = sum(e.get("commission_earned", 0) for e in events)
    active_subs = sum(1 for e in events if e.get("status") == "subscribed")

    tier = _get_tier(total_refs)
    next_tier = _get_next_tier(total_refs)
    all_codes = []
    async for code_row in iter_find_paginated(
        db.referral_codes,
        {},
        {"_id": 0, "total_signups": 1},
        sort=[("total_signups", -1)],
        max_docs=10000,
    ):
        all_codes.append(code_row)
    rank = 1
    for i, c in enumerate(all_codes):
        if c.get("user_id") == uid:
            rank = i + 1
            break
    total_participants = len(all_codes) or 1

    import hashlib

    code = f"RAC-{hashlib.md5(uid.encode()).hexdigest()[:6].upper()}"
    commission_pct = int(tier["commission"] * 100)
    max_refs = 16
    progress_pct = min(int((total_refs / max_refs) * 100), 100)

    next_tier_html = ""
    if next_tier:
        needed = next_tier["min_referrals"] - total_refs
        next_tier_html = f"""
        <div style="background:#0F172A;border:1px solid {next_tier["color"]}33;border-radius:12px;padding:16px;margin-top:12px;">
          <div style="color:#94A3B8;font-size:11px;font-weight:600;text-transform:uppercase;">Next Tier: {next_tier["name"]}</div>
          <div style="color:{next_tier["color"]};font-size:18px;font-weight:800;margin-top:4px;">
            {needed} more referral{"s" if needed != 1 else ""} to unlock {int(next_tier["commission"] * 100)}% commission
          </div>
        </div>
        """

    body = f"""
    <tr><td style="padding:32px 28px 0;">
      <div style="background:#3D2D1A;border:1px solid #B07D20;border-radius:8px;padding:8px 12px;margin-bottom:16px;">
        <span style="color:#F59E0B;font-size:12px;font-weight:700;">TEST EMAIL</span>
        <span style="color:#94A3B8;font-size:12px;"> - This is a preview of the weekly referral digest</span>
      </div>
      <div style="font-size:24px;font-weight:800;color:#F8FAFC;letter-spacing:-0.5px;">
        Hi {name}!
      </div>
      <div style="color:#94A3B8;font-size:14px;margin-top:8px;">
        Your weekly referral digest is here. Here's how you're doing.
      </div>
    </td></tr>

    <tr><td style="padding:24px 28px 0;">
      <div style="background:#1E293B;border-radius:14px;padding:24px;border:1px solid {tier["color"]}40;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="vertical-align:top;">
              <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Your Tier</div>
              <div style="color:{tier["color"]};font-size:26px;font-weight:900;">{tier["name"]}</div>
              <div style="color:#94A3B8;font-size:12px;">{commission_pct}% commission rate</div>
            </td>
            <td style="text-align:right;vertical-align:top;">
              <div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Rank</div>
              <div style="color:#F8FAFC;font-size:28px;font-weight:900;">#{rank}</div>
              <div style="color:#64748B;font-size:10px;">of {total_participants}</div>
            </td>
          </tr>
        </table>
        <div style="margin-top:16px;">
          <div style="color:#94A3B8;font-size:11px;margin-bottom:6px;">{total_refs} referrals &middot; {progress_pct}% to Gold</div>
          <div style="height:8px;background:#0F172A;border-radius:4px;overflow:hidden;">
            <div style="height:100%;width:{max(progress_pct, 3)}%;background:{tier["color"]};border-radius:4px;"></div>
          </div>
        </div>
        {next_tier_html}
      </div>
    </td></tr>

    <tr><td style="padding:24px 28px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="width:33%;padding:6px;"><div style="background:#0F172A;border:1px solid #1E293B;border-radius:12px;padding:16px;text-align:center;border-left:3px solid #2563EB;"><div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Referrals</div><div style="color:#F8FAFC;font-size:28px;font-weight:800;margin-top:4px;">{total_refs}</div></div></td>
          <td style="width:33%;padding:6px;"><div style="background:#0F172A;border:1px solid #1E293B;border-radius:12px;padding:16px;text-align:center;border-left:3px solid #059669;"><div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Active Subs</div><div style="color:#F8FAFC;font-size:28px;font-weight:800;margin-top:4px;">{active_subs}</div></div></td>
          <td style="width:33%;padding:6px;"><div style="background:#0F172A;border:1px solid #1E293B;border-radius:12px;padding:16px;text-align:center;border-left:3px solid #8B5CF6;"><div style="color:#64748B;font-size:10px;font-weight:600;text-transform:uppercase;">Earned</div><div style="color:#F8FAFC;font-size:28px;font-weight:800;margin-top:4px;">${total_earnings:.2f}</div></div></td>
        </tr>
      </table>
    </td></tr>

    <tr><td style="padding:24px 28px 0;">
      <div style="background:#1E293B;border-radius:12px;padding:18px;border:1px solid #334155;">
        <div style="color:#64748B;font-size:10px;font-weight:700;text-transform:uppercase;margin-bottom:8px;">Your Referral Code</div>
        <div style="color:#2563EB;font-size:22px;font-weight:800;letter-spacing:2px;">{code}</div>
      </div>
    </td></tr>

    <tr><td style="padding:28px 28px 0;text-align:center;">
      <a href="https://realaicoach.app/referrals" style="display:inline-block;background:{tier["color"]};color:#ffffff;font-size:16px;font-weight:700;padding:16px 40px;border-radius:12px;text-decoration:none;">
        View My Dashboard
      </a>
    </td></tr>
    """

    html = _wrap("[TEST] Your Weekly Referral Digest", "Preview of your weekly referral stats", body)

    result = {"success": True, "email": email, "message": "Test email sent"}
    if is_email_configured():
        await send_email(email, f"[TEST] Referral Digest: Rank #{rank} | {tier['name']} Tier", html, template_key="referral_digest_test")
    else:
        result["message"] = "Email service not configured. Preview generated but not sent."

    return result


async def admin_seed_demo_data(request: Request):
    """Seed demo referral data for testing."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    demo_referrers = [
        {"user_id": "user_demo_001", "name": "Sarah Chen", "email": "sarah@demo.com", "code": "RAC-SC001"},
        {"user_id": "user_demo_002", "name": "James Wilson", "email": "james@demo.com", "code": "RAC-JW002"},
        {"user_id": "user_demo_003", "name": "Maria Garcia", "email": "maria@demo.com", "code": "RAC-MG003"},
        {"user_id": "user_demo_004", "name": "David Kim", "email": "david@demo.com", "code": "RAC-DK004"},
        {"user_id": "user_demo_005", "name": "Emily Taylor", "email": "emily@demo.com", "code": "RAC-ET005"},
    ]
    import random

    statuses = ["signed_up", "subscribed", "subscribed", "subscribed", "signed_up", "subscribed"]
    plans = ["free", "basic", "basic", "premium", "premium", "basic", "premium"]
    seeded = 0

    for ref in demo_referrers:
        existing = await db.referral_codes.find_one({"code": ref["code"]})
        if existing:
            continue
        clicks = random.randint(15, 120)
        signups = random.randint(3, min(clicks // 3, 20))
        await db.referral_codes.insert_one(
            {
                **ref,
                "total_clicks": clicks,
                "total_signups": signups,
                "active_subscribers": random.randint(1, signups),
                "total_earnings": 0,
                "pending_earnings": 0,
                "paid_earnings": 0,
                "created_at": (now - timedelta(days=random.randint(10, 60))).isoformat(),
            }
        )

        for j in range(signups):
            status = random.choice(statuses)
            plan = random.choice(plans)
            commission = PLAN_PRICES.get(plan, 0) * COMMISSION_RATE if status == "subscribed" else 0
            days_ago = random.randint(1, 30)
            created = (now - timedelta(days=days_ago)).isoformat()

            await db.referral_events.insert_one(
                {
                    "referral_id": f"ref_{uuid.uuid4().hex[:12]}",
                    "referrer_id": ref["user_id"],
                    "referrer_code": ref["code"],
                    "referred_user_id": f"user_ref_{uuid.uuid4().hex[:8]}",
                    "referred_email": f"user{j}_{ref['code'].lower()}@example.com",
                    "referred_name": f"Referred User {j + 1}",
                    "status": status,
                    "plan": plan,
                    "commission_earned": round(commission, 2),
                    "created_at": created,
                    "converted_at": created if status == "subscribed" else "",
                }
            )
            seeded += 1

            # Add click log entries
            for _ in range(random.randint(1, 5)):
                click_day = (now - timedelta(days=random.randint(0, 29))).isoformat()
                await db.referral_click_log.insert_one(
                    {
                        "code": ref["code"],
                        "referrer_id": ref["user_id"],
                        "clicked_at": click_day,
                        "ip": f"192.168.1.{random.randint(1, 254)}",
                    }
                )

    return {"success": True, "seeded_events": seeded, "referrers": len(demo_referrers)}


# ═══════════════════════════════════════════════
# ─── Referral Credit / Auto-Renewal System ────
# ═══════════════════════════════════════════════


async def _ensure_wallet(user_id: str) -> dict:
    """Get or create a referral wallet for a user."""
    wallet = await db.referral_wallets.find_one({"user_id": user_id}, {"_id": 0})
    if not wallet:
        wallet = {
            "user_id": user_id,
            "total_earned": 0.0,
            "total_applied": 0.0,
            "balance": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.referral_wallets.insert_one(wallet)
    return wallet


async def credit_referral_earning(
    referrer_id: str,
    amount: float,
    source: str,
    details: dict | None = None,
    dedupe_key: str | None = None,
):
    """Add referral earnings to a user's wallet. Called when a commission is earned."""
    await _ensure_referrals_indexes()
    dedupe_key = str(dedupe_key or "").strip()
    if dedupe_key:
        prior = await db.referral_credit_transactions.find_one(
            {
                "user_id": referrer_id,
                "type": "credit",
                "source": source,
                "dedupe_key": dedupe_key,
            },
            {"_id": 0, "amount": 1},
        )
        if prior:
            return

    await _ensure_wallet(referrer_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.referral_wallets.update_one(
        {"user_id": referrer_id},
        {"$inc": {"total_earned": round(amount, 2), "balance": round(amount, 2)}, "$set": {"updated_at": now_iso}},
    )

    await db.referral_credit_transactions.insert_one(
        {
            "user_id": referrer_id,
            "type": "credit",
            "amount": round(amount, 2),
            "source": source,
            "dedupe_key": dedupe_key or None,
            "details": details or {},
            "balance_after": round((await _ensure_wallet(referrer_id)).get("balance", 0), 2),
            "created_at": now_iso,
        }
    )

    logger.info(f"Referral credit: {referrer_id} +${amount:.2f} from {source}")


async def apply_credits_to_renewal(user_id: str, subscription_cost: float, idempotency_key: str | None = None) -> dict:
    """Automatically apply referral credits to a subscription renewal.
    Returns: {applied: float, remaining_charge: float, fully_covered: bool}
    """
    await _ensure_referrals_indexes()
    wallet = await _ensure_wallet(user_id)
    dedupe_key = str(idempotency_key or "").strip()
    if dedupe_key:
        existing_debit = await db.referral_credit_transactions.find_one(
            {
                "user_id": user_id,
                "type": "debit",
                "source": "subscription_renewal",
                "dedupe_key": dedupe_key,
            },
            {"_id": 0, "details": 1},
        )
        if existing_debit:
            details = existing_debit.get("details") or {}
            return {
                "applied": round(float(details.get("credits_applied") or 0), 2),
                "remaining_charge": round(float(details.get("remaining_charge") or subscription_cost), 2),
                "fully_covered": bool(details.get("fully_covered")),
                "already_processed": True,
            }

    balance = wallet.get("balance", 0)

    if balance <= 0:
        return {"applied": 0, "remaining_charge": subscription_cost, "fully_covered": False}

    applied = min(balance, subscription_cost)
    remaining = subscription_cost - applied
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.referral_wallets.update_one(
        {"user_id": user_id},
        {"$inc": {"total_applied": round(applied, 2), "balance": -round(applied, 2)}, "$set": {"updated_at": now_iso}},
    )

    await db.referral_credit_transactions.insert_one(
        {
            "user_id": user_id,
            "type": "debit",
            "amount": round(applied, 2),
            "source": "subscription_renewal",
            "dedupe_key": dedupe_key or None,
            "details": {
                "subscription_cost": subscription_cost,
                "credits_applied": round(applied, 2),
                "remaining_charge": round(remaining, 2),
                "fully_covered": remaining <= 0,
            },
            "balance_after": round(balance - applied, 2),
            "created_at": now_iso,
        }
    )

    # Notify user about credit application
    from utils.notification_helper import create_notification

    if remaining <= 0:
        msg = f"Your subscription renewal of ${subscription_cost:.2f} was fully covered by your referral credits!"
    else:
        msg = f"${applied:.2f} in referral credits applied to your renewal. Remaining charge: ${remaining:.2f}"

    await create_notification(
        user_id=user_id,
        title="Referral Credits Applied!",
        message=msg,
        notif_type="referral_credit_applied",
        data={"applied": round(applied, 2), "remaining": round(remaining, 2)},
    )

    logger.info(f"Referral credit applied: {user_id} -${applied:.2f} for renewal (remaining: ${remaining:.2f})")
    return {"applied": round(applied, 2), "remaining_charge": round(remaining, 2), "fully_covered": remaining <= 0}


# ─── User: My Credit Balance ───


@router.get("/my-credits")
async def get_my_credits(request: Request):
    """Get current user's referral credit balance and recent transactions."""
    user = await require_auth(request)
    wallet = await _ensure_wallet(user.user_id)

    # Recent transactions
    txns = (
        await db.referral_credit_transactions.find({"user_id": user.user_id}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(20)
    )

    # Upcoming renewal info
    user_doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "subscription_plan": 1, "subscription_end_date": 1}
    )
    plan = (user_doc or {}).get("subscription_plan", "free")
    end_date = (user_doc or {}).get("subscription_end_date")
    plan_cost = PLAN_PRICES.get(plan, 0)
    balance = wallet.get("balance", 0)

    renewal_info = None
    if plan != "free" and end_date:
        renewal_info = {
            "plan": plan,
            "cost": plan_cost,
            "renewal_date": end_date,
            "credits_available": round(balance, 2),
            "credits_will_cover": round(min(balance, plan_cost), 2),
            "remaining_after_credits": round(max(plan_cost - balance, 0), 2),
            "fully_covered": balance >= plan_cost,
        }

    return {
        "balance": round(balance, 2),
        "total_earned": round(wallet.get("total_earned", 0), 2),
        "total_applied": round(wallet.get("total_applied", 0), 2),
        "transactions": txns,
        "renewal_info": renewal_info,
    }


# ─── Admin: Credit System Analytics ───


@router.get("/admin/credit-analytics")
async def admin_credit_analytics(request: Request):
    """Admin dashboard for referral credit system."""
    await require_admin(request)

    total_wallets = await db.referral_wallets.count_documents({})
    wallets_with_balance = await db.referral_wallets.count_documents({"balance": {"$gt": 0}})

    # Aggregation for totals
    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_earned": {"$sum": "$total_earned"},
                "total_applied": {"$sum": "$total_applied"},
                "total_balance": {"$sum": "$balance"},
            }
        }
    ]
    agg = await db.referral_wallets.aggregate(pipeline).to_list(1)
    totals = agg[0] if agg else {"total_earned": 0, "total_applied": 0, "total_balance": 0}

    # Credit vs debit breakdown
    credit_txns = await db.referral_credit_transactions.count_documents({"type": "credit"})
    debit_txns = await db.referral_credit_transactions.count_documents({"type": "debit"})

    # Recent transactions (platform-wide)
    recent = await db.referral_credit_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)

    # Enrich with user names
    recent_user_ids = [str(txn.get("user_id") or "") for txn in recent]
    recent_users_map = await _load_user_profiles(recent_user_ids)
    for txn in recent:
        profile = recent_users_map.get(str(txn.get("user_id") or ""), {})
        txn["user_name"] = str(profile.get("name") or "Unknown")
        txn["user_email"] = str(profile.get("email") or "")

    # Top wallets by balance
    top_wallets = await db.referral_wallets.find({"balance": {"$gt": 0}}, {"_id": 0}).sort("balance", -1).to_list(10)
    top_wallet_user_ids = [str(w.get("user_id") or "") for w in top_wallets]
    top_wallet_users_map = await _load_user_profiles(top_wallet_user_ids)
    for w in top_wallets:
        profile = top_wallet_users_map.get(str(w.get("user_id") or ""), {})
        w["name"] = str(profile.get("name") or "Unknown")
        w["email"] = str(profile.get("email") or "")
        w["plan"] = str(profile.get("subscription_plan") or "free")

    # Monthly credit application trend (last 6 months)
    now = datetime.now(timezone.utc)
    monthly_trend = []
    for i in range(6):
        month_start = (now.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        credits = await db.referral_credit_transactions.aggregate(
            [
                {"$match": {"created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}}},
                {"$group": {"_id": "$type", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            ]
        ).to_list(5)
        earned = next((c["total"] for c in credits if c["_id"] == "credit"), 0)
        applied = next((c["total"] for c in credits if c["_id"] == "debit"), 0)
        monthly_trend.append(
            {
                "month": month_start.strftime("%b %Y"),
                "earned": round(earned, 2),
                "applied": round(applied, 2),
            }
        )
    monthly_trend.reverse()

    # Upcoming renewals that have credits
    renewal_eligible = []
    users_with_subs = await db.users.find(
        {"subscription_plan": {"$ne": "free"}, "subscription_end_date": {"$exists": True}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "subscription_plan": 1, "subscription_end_date": 1},
    ).to_list(100)
    for u in users_with_subs:
        w = await db.referral_wallets.find_one({"user_id": u["user_id"]}, {"_id": 0, "balance": 1})
        bal = (w or {}).get("balance", 0)
        if bal > 0:
            cost = PLAN_PRICES.get(u.get("subscription_plan", "free"), 0)
            renewal_eligible.append(
                {
                    "user_id": u["user_id"],
                    "name": u.get("name", "Unknown"),
                    "email": u.get("email", ""),
                    "plan": u.get("subscription_plan"),
                    "renewal_date": u.get("subscription_end_date"),
                    "plan_cost": cost,
                    "credit_balance": round(bal, 2),
                    "will_cover": round(min(bal, cost), 2),
                    "fully_covered": bal >= cost,
                }
            )

    return {
        "total_wallets": total_wallets,
        "wallets_with_balance": wallets_with_balance,
        "total_earned": round(totals.get("total_earned", 0), 2),
        "total_applied": round(totals.get("total_applied", 0), 2),
        "total_pending_balance": round(totals.get("total_balance", 0), 2),
        "credit_transactions": credit_txns,
        "debit_transactions": debit_txns,
        "recent_transactions": recent,
        "top_wallets": top_wallets,
        "monthly_trend": monthly_trend,
        "upcoming_renewals": renewal_eligible,
        "automation_status": "active",
        "description": "Credits earned from referrals are automatically applied to subscription renewals. No manual intervention needed.",
    }


@router.get("/admin/ops-health")
async def admin_referrals_ops_health(request: Request):
    """Operational health snapshot for referral reliability and payout integrity."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    since_24h = (now - timedelta(hours=24)).isoformat()

    total_signups = await db.referral_events.count_documents({"status": "signed_up"})
    total_subscribed = await db.referral_events.count_documents({"status": "subscribed"})

    conversion_rate = round((total_subscribed / max(total_signups + total_subscribed, 1)) * 100, 2)

    replay_24h = await db.referral_idempotency.count_documents({"updated_at": {"$gte": since_24h}})
    duplicate_credit_rows = await db.referral_credit_transactions.aggregate(
        [
            {
                "$match": {
                    "type": "credit",
                    "dedupe_key": {"$exists": True, "$nin": [None, ""]},
                    "created_at": {"$gte": since_24h},
                }
            },
            {"$group": {"_id": "$dedupe_key", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "duplicates"},
        ]
    ).to_list(1)

    latest_scan = await db.referral_fraud_scan_history.find_one({}, {"_id": 0}, sort=[("scan_time", -1)])

    return {
        "generated_at": now.isoformat(),
        "flags": {
            "payouts_enabled": REFERRALS_PAYOUTS_ENABLED,
            "fraud_autoscan_enabled": REFERRALS_FRAUD_AUTOSCAN_ENABLED,
        },
        "funnel": {
            "signed_up": total_signups,
            "subscribed": total_subscribed,
            "conversion_rate": conversion_rate,
        },
        "idempotency": {
            "replay_records_last_24h": replay_24h,
            "duplicate_credit_dedupe_keys_last_24h": int((duplicate_credit_rows[0] if duplicate_credit_rows else {}).get("duplicates") or 0),
        },
        "fraud": {
            "last_scan_time": str((latest_scan or {}).get("scan_time") or ""),
            "last_scan_type": str((latest_scan or {}).get("scan_type") or ""),
            "last_scan_alerts": int((latest_scan or {}).get("alerts_generated") or 0),
        },
    }


@router.post("/admin/integrity-alerts/evaluate")
async def admin_run_integrity_alert_evaluation(request: Request):
    admin_user = await require_admin(request)
    _assert_rate_limit(
        request,
        "integrity_alert_eval",
        limit=6,
        window_seconds=300,
        actor_hint=str(getattr(admin_user, "user_id", "admin")),
    )
    result = await evaluate_and_emit_referral_integrity_alerts(trigger="manual")
    return result


@router.get("/admin/integrity-alerts")
async def admin_referral_integrity_alerts(
    request: Request,
    status: str = Query("open"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    await require_admin(request)
    now = datetime.now(timezone.utc)
    filter_doc: dict[str, Any] = {}
    if status in {"open", "resolved"}:
        filter_doc["status"] = status

    total_count = await db.referral_integrity_alerts.count_documents(filter_doc)
    skip = (page - 1) * page_size
    alerts = (
        await db.referral_integrity_alerts.find(filter_doc, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size)
    )

    enriched_alerts = [_enrich_integrity_alert(alert, now) for alert in alerts]

    return {
        "alerts": enriched_alerts,
        "data": enriched_alerts,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "status": status,
    }


@router.post("/admin/integrity-alerts/{alert_id}/resolve")
async def admin_resolve_integrity_alert(request: Request, alert_id: str):
    admin_user = await require_admin(request)
    body = await request.json()
    resolution = str(body.get("resolution") or "acknowledged").strip() or "acknowledged"
    result = await db.referral_integrity_alerts.update_one(
        {"alert_id": alert_id},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": str(getattr(admin_user, "email", "admin")),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Integrity alert not found")
    return {"success": True, "alert_id": alert_id, "resolution": resolution}


@router.post("/admin/integrity-alerts/{alert_id}/apply-suggestion")
async def admin_apply_integrity_alert_suggestion(request: Request, alert_id: str):
    admin_user = await require_admin(request)
    alert = await db.referral_integrity_alerts.find_one({"alert_id": alert_id}, {"_id": 0})
    if not alert:
        raise HTTPException(404, "Integrity alert not found")

    suggestion = _build_integrity_alert_suggestion(alert, datetime.now(timezone.utc))
    if not suggestion:
        raise HTTPException(400, "No auto-resolution suggestion is currently available for this alert")

    resolution = str(suggestion.get("resolution") or "auto_resolved_stale_low_severity")
    result = await db.referral_integrity_alerts.update_one(
        {"alert_id": alert_id, "status": "open"},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolution_source": "suggestion",
                "suggestion_applied": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": str(getattr(admin_user, "email", "admin")),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(409, "Integrity alert is no longer open")

    return {
        "success": True,
        "alert_id": alert_id,
        "resolution": resolution,
        "applied_suggestion": suggestion,
    }


@router.get("/admin/integrity-trends")
async def admin_referral_integrity_trends(request: Request, days: int = Query(90, ge=7, le=90)):
    await require_admin(request)
    now = datetime.now(timezone.utc)
    points = []
    for i in range(days - 1, -1, -1):
        day_start_dt = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_dt = day_start_dt + timedelta(days=1)
        day_start = day_start_dt.isoformat()
        day_end = day_end_dt.isoformat()

        signups = await db.referral_events.count_documents({"created_at": {"$gte": day_start, "$lt": day_end}})
        subscribed = await db.referral_events.count_documents(
            {"status": "subscribed", "converted_at": {"$gte": day_start, "$lt": day_end}}
        )
        duplicate_rows = await db.referral_credit_transactions.aggregate(
            [
                {
                    "$match": {
                        "type": "credit",
                        "dedupe_key": {"$exists": True, "$nin": [None, ""]},
                        "created_at": {"$gte": day_start, "$lt": day_end},
                    }
                },
                {"$group": {"_id": "$dedupe_key", "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}},
                {"$count": "duplicates"},
            ]
        ).to_list(1)
        duplicate_keys = int((duplicate_rows[0] if duplicate_rows else {}).get("duplicates") or 0)

        open_alerts = await db.referral_integrity_alerts.count_documents(
            {"status": "open", "created_at": {"$gte": day_start, "$lt": day_end}}
        )
        conversion_quality = round((subscribed / max(signups, 1)) * 100, 2)

        points.append(
            {
                "date": day_start_dt.strftime("%Y-%m-%d"),
                "signups": signups,
                "subscribed": subscribed,
                "conversion_quality": conversion_quality,
                "duplicate_prevention_breaches": duplicate_keys,
                "open_integrity_alerts": open_alerts,
            }
        )

    def _window_summary(window_days: int) -> dict[str, Any]:
        window = points[-window_days:]
        total_signups = sum(int(p["signups"]) for p in window)
        total_subscribed = sum(int(p["subscribed"]) for p in window)
        total_duplicates = sum(int(p["duplicate_prevention_breaches"]) for p in window)
        avg_quality = round(sum(float(p["conversion_quality"]) for p in window) / max(len(window), 1), 2)
        return {
            "days": window_days,
            "avg_conversion_quality": avg_quality,
            "total_signups": total_signups,
            "total_subscribed": total_subscribed,
            "duplicate_prevention_breaches": total_duplicates,
        }

    return {
        "days": days,
        "points": points,
        "windows": {
            "7": _window_summary(7),
            "30": _window_summary(30),
            "90": _window_summary(min(90, len(points))),
        },
        "generated_at": now.isoformat(),
    }


@router.get("/admin/integrity-incident-timeline")
async def admin_referral_integrity_incident_timeline(request: Request, limit: int = Query(12, ge=1, le=30)):
    await require_admin(request)
    timeline = await _build_integrity_incident_timeline(limit)
    return {
        "timeline": timeline,
        "count": len(timeline),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/fraud-policy/recommendation")
async def admin_fraud_policy_recommendation(request: Request):
    await require_admin(request)
    now = datetime.now(timezone.utc)
    metrics = await _compute_integrity_metrics(now)
    recommendation = _recommend_fraud_profile(metrics)
    active_policy = await db.referral_fraud_policy.find_one({"policy_key": "active"}, {"_id": 0})
    active_profile = str((active_policy or {}).get("profile") or "balanced")
    return {
        "active_profile": active_profile,
        "recommendation": recommendation,
        "metrics": metrics,
        "is_change_required": active_profile != recommendation["recommended_profile"],
        "evaluated_at": now.isoformat(),
    }


@router.post("/admin/fraud-policy/apply-recommendation")
async def admin_apply_fraud_policy_recommendation(request: Request):
    admin_user = await require_admin(request)
    body = await request.json()
    requested_profile = str(body.get("profile") or "").strip().lower()
    now = datetime.now(timezone.utc)

    if requested_profile not in FRAUD_POLICY_PROFILES:
        metrics = await _compute_integrity_metrics(now)
        recommendation = _recommend_fraud_profile(metrics)
        requested_profile = recommendation["recommended_profile"]

    rules = FRAUD_POLICY_PROFILES[requested_profile]
    await db.referral_fraud_policy.update_one(
        {"policy_key": "active"},
        {
            "$set": {
                "policy_key": "active",
                "profile": requested_profile,
                "rules": rules,
                "updated_at": now.isoformat(),
                "updated_by": str(getattr(admin_user, "email", "admin")),
            },
            "$setOnInsert": {"created_at": now.isoformat()},
        },
        upsert=True,
    )

    await db.referral_fraud_policy_audit.insert_one(
        {
            "audit_id": f"rfp_{uuid.uuid4().hex[:10]}",
            "profile": requested_profile,
            "rules": rules,
            "changed_by": str(getattr(admin_user, "email", "admin")),
            "changed_at": now.isoformat(),
            "reason": "one_click_apply_recommendation",
        }
    )

    return {
        "success": True,
        "applied_profile": requested_profile,
        "rules": rules,
        "updated_at": now.isoformat(),
    }


# ─── Auto-apply credits on simulated renewal ───


@router.post("/auto-apply-renewal")
async def auto_apply_renewal_credits(request: Request):
    """Simulate/trigger automatic credit application for a user's next renewal.
    In production, this would be called by the payment webhook or scheduler.
    """
    user = await require_auth(request)
    uid = user.user_id
    _assert_rate_limit(request, "auto_apply_renewal", limit=10, window_seconds=300, actor_hint=uid)

    idem = _normalize_idempotency_key(request.headers.get("x-idempotency-key"))
    if not idem:
        idem = _make_idempotency_fingerprint(uid, "auto_apply_renewal", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    replay = await _get_idempotency_replay("auto_apply_renewal", uid, idem)
    if replay:
        return {**replay, "idempotent_replay": True}

    user_doc = await db.users.find_one({"user_id": uid}, {"_id": 0, "subscription_plan": 1})
    plan = (user_doc or {}).get("subscription_plan", "free")
    cost = PLAN_PRICES.get(plan, 0)

    if plan == "free" or cost <= 0:
        return {"success": False, "message": "No active subscription to renew"}

    result = await apply_credits_to_renewal(uid, cost, idempotency_key=idem)
    response = {"success": True, **result}
    await _save_idempotency_replay("auto_apply_renewal", uid, idem, response)
    return response


# ═══════════════════════════════════════════════
# ─── Milestone Rewards Endpoints ──────────────
# ═══════════════════════════════════════════════


@router.get("/my-milestones")
async def get_my_milestones(request: Request):
    """Get current user's milestone progress and achievements."""
    user = await require_auth(request)
    uid = user.user_id

    # Get total signups
    code_doc = await db.referral_codes.find_one({"user_id": uid}, {"_id": 0, "total_signups": 1})
    total_signups = (code_doc or {}).get("total_signups", 0)

    # Get achieved milestones
    achieved = await db.referral_milestones.find({"user_id": uid}, {"_id": 0}).to_list(50)
    achieved_ids = {a["milestone_id"] for a in achieved}
    achieved_map = {a["milestone_id"]: a for a in achieved}

    milestones = []
    for m in MILESTONES:
        is_achieved = m["id"] in achieved_ids
        progress = min(total_signups / m["referrals"], 1.0)
        entry = {
            "id": m["id"],
            "label": m["label"],
            "icon": m["icon"],
            "color": m["color"],
            "referrals_required": m["referrals"],
            "bonus": m["bonus"],
            "achieved": is_achieved,
            "progress": round(progress, 2),
            "referrals_remaining": max(m["referrals"] - total_signups, 0),
        }
        if is_achieved:
            entry["achieved_at"] = achieved_map[m["id"]].get("achieved_at", "")
        milestones.append(entry)

    # Next milestone
    next_milestone = None
    for m in MILESTONES:
        if m["id"] not in achieved_ids:
            next_milestone = {
                "id": m["id"],
                "label": m["label"],
                "referrals_required": m["referrals"],
                "referrals_remaining": m["referrals"] - total_signups,
                "bonus": m["bonus"],
                "progress": round(min(total_signups / m["referrals"], 1.0), 2),
            }
            break

    total_bonus_earned = sum(m["bonus"] for m in MILESTONES if m["id"] in achieved_ids)

    return {
        "milestones": milestones,
        "total_signups": total_signups,
        "total_achieved": len(achieved_ids),
        "total_bonus_earned": round(total_bonus_earned, 2),
        "next_milestone": next_milestone,
    }


@router.get("/admin/milestone-analytics")
async def admin_milestone_analytics(request: Request):
    """Admin analytics for milestone rewards system."""
    await require_admin(request)

    # Total milestone achievements
    total_achievements = await db.referral_milestones.count_documents({})

    # Per-milestone breakdown
    milestone_counts = []
    total_bonus_paid = 0
    for m in MILESTONES:
        count = await db.referral_milestones.count_documents({"milestone_id": m["id"]})
        milestone_counts.append(
            {
                "id": m["id"],
                "label": m["label"],
                "icon": m["icon"],
                "color": m["color"],
                "referrals_required": m["referrals"],
                "bonus": m["bonus"],
                "achievers": count,
                "total_paid": round(m["bonus"] * count, 2),
            }
        )
        total_bonus_paid += m["bonus"] * count

    # Unique users with milestones
    unique_users = len(await db.referral_milestones.distinct("user_id"))

    # Recent achievements
    recent = await db.referral_milestones.find({}, {"_id": 0}).sort("achieved_at", -1).to_list(15)
    for r in recent:
        u = await db.users.find_one({"user_id": r.get("user_id")}, {"_id": 0, "name": 1, "email": 1})
        r["user_name"] = (u or {}).get("name", "Unknown")
        r["user_email"] = (u or {}).get("email", "")

    return {
        "total_achievements": total_achievements,
        "unique_achievers": unique_users,
        "total_bonus_paid": round(total_bonus_paid, 2),
        "milestones": milestone_counts,
        "recent_achievements": recent,
        "all_milestones": MILESTONES,
    }


# ─── Sharing Kit ───


@router.get("/sharing-kit")
async def get_sharing_kit(request: Request):
    """Get pre-written social media templates and QR code for referral sharing."""
    user = await require_auth(request)
    uid = user.user_id
    code = _gen_code(uid)
    base_url = (
        request.headers.get("origin", "")
        or request.headers.get("referer", "").split("?")[0].rstrip("/")
        or "https://realaicoach.app"
    )
    referral_link = f"{base_url}?ref={code}"
    user_name = user.name or "a friend"
    nl = "\n"

    # Channel-specific referral links
    def ch_link(channel: str) -> str:
        return f"{referral_link}&ch={channel}"

    # Define qr_link first (QR code includes &ch=qr parameter)
    qr_link = ch_link("qr")

    # Generate QR code as base64
    import qrcode
    import io
    import base64

    qr = qrcode.QRCode(version=1, box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    # Pre-compute template texts
    tw_link = ch_link("twitter")
    twitter_text = (
        "I've been using RealAICoach to accelerate my career growth "
        "and it's been a game-changer! Use my link to get 15% off "
        f"your subscription. {tw_link} #AICoaching #CareerGrowth"
    )
    li_link = ch_link("linkedin")
    linkedin_text = (
        "I wanted to share a tool that's been instrumental in my "
        f"professional development - RealAICoach.{nl}{nl}"
        "It offers AI-powered coaching, real-time analytics, and "
        "personalized growth plans that have helped me sharpen my "
        f"leadership skills and stay ahead in my career.{nl}{nl}"
        "If you're looking to invest in your growth, use my referral "
        f"link for 15% off:{nl}{li_link}{nl}{nl}"
        "#ProfessionalDevelopment #AICoaching #Leadership"
    )
    wa_link = ch_link("whatsapp")
    whatsapp_text = (
        "Hey! I've been using this amazing AI coaching platform called "
        "RealAICoach. It's helped me a lot with career growth and skill "
        "development. You should check it out - you'll get 15% off with "
        f"my referral link: {wa_link}"
    )
    em_link = ch_link("email")
    email_subject = f"{user_name} thinks you'll love RealAICoach - Get 15% Off!"
    email_body = (
        f"Hi there,{nl}{nl}"
        "I've been using RealAICoach for my professional development, "
        f"and I thought you might find it valuable too.{nl}{nl}"
        "It's an AI-powered coaching platform with live tools including "
        "real-time analytics, personalized growth plans, and career "
        "coaching. It's genuinely helped me improve my skills and stay "
        f"on track with my goals.{nl}{nl}"
        "As a friend, I can offer you 15% off your subscription if "
        f"you sign up through my referral link:{nl}{em_link}{nl}{nl}"
        f"Feel free to explore it - I think you'll love it!{nl}{nl}"
        f"Best,{nl}{user_name}"
    )
    sm_link = ch_link("sms")
    sms_text = (
        "Hey! Check out RealAICoach - AI-powered career coaching "
        f"that's been really helpful for me. Get 15% off with my link: {sm_link}"
    )

    templates = {
        "twitter": {
            "platform": "Twitter / X",
            "icon": "logo-twitter",
            "color": "#1DA1F2",
            "text": twitter_text,
            "share_url": f"https://twitter.com/intent/tweet?text={url_quote(twitter_text)}",
            "char_limit": 280,
        },
        "linkedin": {
            "platform": "LinkedIn",
            "icon": "logo-linkedin",
            "color": "#0A66C2",
            "text": linkedin_text,
            "share_url": f"https://www.linkedin.com/sharing/share-offsite/?url={url_quote(referral_link)}",
            "char_limit": 3000,
        },
        "whatsapp": {
            "platform": "WhatsApp",
            "icon": "logo-whatsapp",
            "color": "#25D366",
            "text": whatsapp_text,
            "share_url": f"https://wa.me/?text={url_quote(whatsapp_text)}",
            "char_limit": None,
        },
        "email": {
            "platform": "Email",
            "icon": "mail",
            "color": "#6366F1",
            "subject": email_subject,
            "text": email_body,
            "share_url": f"mailto:?subject={url_quote(email_subject)}&body={url_quote(email_body)}",
            "char_limit": None,
        },
        "sms": {
            "platform": "SMS",
            "icon": "chatbubble",
            "color": "#10B981",
            "text": sms_text,
            "share_url": f"sms:?body={url_quote(sms_text)}",
            "char_limit": 160,
        },
    }

    return {
        "referral_code": code,
        "referral_link": referral_link,
        "qr_code": qr_base64,
        "templates": templates,
    }


# ─── Channel Analytics ───

CHANNEL_META = {
    "twitter": {"label": "Twitter / X", "icon": "logo-twitter", "color": "#1DA1F2"},
    "linkedin": {"label": "LinkedIn", "icon": "logo-linkedin", "color": "#0A66C2"},
    "whatsapp": {"label": "WhatsApp", "icon": "logo-whatsapp", "color": "#25D366"},
    "email": {"label": "Email", "icon": "mail", "color": "#6366F1"},
    "sms": {"label": "SMS", "icon": "chatbubble", "color": "#10B981"},
    "qr": {"label": "QR Code", "icon": "qr-code", "color": "#F59E0B"},
    "direct": {"label": "Direct Link", "icon": "link", "color": "#8B5CF6"},
}


@router.get("/my-channel-analytics")
async def my_channel_analytics(request: Request):
    """Get the authenticated user's referral channel performance."""
    user = await require_auth(request)
    uid = user.user_id

    # Aggregate by channel
    channels = {}
    for ch_key in CHANNEL_META:
        channels[ch_key] = {"clicks": 0, "signups": 0, "subscriptions": 0, "revenue": 0}

    async for c in iter_find_paginated(
        db.referral_click_log,
        {"referrer_id": uid},
        {"_id": 0},
        max_docs=10000,
    ):
        ch = c.get("channel", "direct")
        if ch not in channels:
            channels[ch] = {"clicks": 0, "signups": 0, "subscriptions": 0, "revenue": 0}
        channels[ch]["clicks"] += 1

    async for e in iter_find_paginated(
        db.referral_events,
        {"referrer_id": uid},
        {"_id": 0},
        max_docs=5000,
    ):
        ch = e.get("channel", "direct")
        if ch not in channels:
            channels[ch] = {"clicks": 0, "signups": 0, "subscriptions": 0, "revenue": 0}
        channels[ch]["signups"] += 1
        if e.get("status") == "subscribed":
            channels[ch]["subscriptions"] += 1
            channels[ch]["revenue"] += e.get("commission_earned", 0)

    # Build response with meta
    channel_data = []
    total_signups = sum(c["signups"] for c in channels.values())
    best_channel = None
    best_signups = 0
    for ch_key, stats in channels.items():
        meta = CHANNEL_META.get(ch_key, {"label": ch_key.title(), "icon": "globe", "color": "#64748B"})
        conversion_rate = round(stats["signups"] / stats["clicks"] * 100, 1) if stats["clicks"] > 0 else 0
        share_pct = round(stats["signups"] / total_signups * 100, 1) if total_signups > 0 else 0
        entry = {
            "channel": ch_key,
            **meta,
            **stats,
            "revenue": round(stats["revenue"], 2),
            "conversion_rate": conversion_rate,
            "share_pct": share_pct,
        }
        channel_data.append(entry)
        if stats["signups"] > best_signups:
            best_signups = stats["signups"]
            best_channel = ch_key

    # Sort by signups descending
    channel_data.sort(key=lambda x: x["signups"], reverse=True)

    return {
        "channels": channel_data,
        "total_signups": total_signups,
        "total_clicks": sum(c["clicks"] for c in channels.values()),
        "best_channel": best_channel,
        "best_channel_label": CHANNEL_META.get(best_channel, {}).get("label", "") if best_channel else "",
    }


@router.get("/admin/channel-analytics")
async def admin_channel_analytics(request: Request):
    """Get platform-wide referral channel analytics for admins."""
    await require_admin(request)

    # Aggregate by channel
    channels = {}
    event_samples = []
    for ch_key in CHANNEL_META:
        channels[ch_key] = {"clicks": 0, "signups": 0, "subscriptions": 0, "revenue": 0, "referrers": set()}

    async for c in iter_find_paginated(db.referral_click_log, {}, {"_id": 0, "channel": 1}):
        ch = c.get("channel", "direct")
        if ch not in channels:
            channels[ch] = {"clicks": 0, "signups": 0, "subscriptions": 0, "revenue": 0, "referrers": set()}
        channels[ch]["clicks"] += 1

    async for e in iter_find_paginated(
        db.referral_events,
        {},
        {"_id": 0, "channel": 1, "status": 1, "commission_earned": 1, "referrer_id": 1, "created_at": 1},
        max_docs=10000,
    ):
        event_samples.append({"channel": e.get("channel", "direct"), "created_at": e.get("created_at", "")})
        ch = e.get("channel", "direct")
        if ch not in channels:
            channels[ch] = {"clicks": 0, "signups": 0, "subscriptions": 0, "revenue": 0, "referrers": set()}
        channels[ch]["signups"] += 1
        channels[ch]["referrers"].add(e.get("referrer_id", ""))
        if e.get("status") == "subscribed":
            channels[ch]["subscriptions"] += 1
            channels[ch]["revenue"] += e.get("commission_earned", 0)

    total_signups = sum(c["signups"] for c in channels.values())
    total_clicks = sum(c["clicks"] for c in channels.values())
    total_revenue = sum(c["revenue"] for c in channels.values())

    channel_data = []
    best_channel = None
    best_signups = 0
    for ch_key, stats in channels.items():
        meta = CHANNEL_META.get(ch_key, {"label": ch_key.title(), "icon": "globe", "color": "#64748B"})
        conversion_rate = round(stats["signups"] / stats["clicks"] * 100, 1) if stats["clicks"] > 0 else 0
        share_pct = round(stats["signups"] / total_signups * 100, 1) if total_signups > 0 else 0
        entry = {
            "channel": ch_key,
            **meta,
            "clicks": stats["clicks"],
            "signups": stats["signups"],
            "subscriptions": stats["subscriptions"],
            "revenue": round(stats["revenue"], 2),
            "unique_referrers": len(stats["referrers"]),
            "conversion_rate": conversion_rate,
            "share_pct": share_pct,
        }
        channel_data.append(entry)
        if stats["signups"] > best_signups:
            best_signups = stats["signups"]
            best_channel = ch_key

    channel_data.sort(key=lambda x: x["signups"], reverse=True)

    # Weekly trend by channel (last 4 weeks)
    now = datetime.now(timezone.utc)
    weekly_trend = []
    for w in range(4):
        week_start = (now - timedelta(weeks=4 - w)).isoformat()
        week_end = (now - timedelta(weeks=3 - w)).isoformat() if w < 3 else now.isoformat()
        week_label = (now - timedelta(weeks=4 - w)).strftime("Week %U")
        week_data = {"week": week_label}
        for ch_key in CHANNEL_META:
            week_data[ch_key] = sum(
                1
                for e in event_samples
                if e.get("channel", "direct") == ch_key and week_start <= e.get("created_at", "") <= week_end
            )
        weekly_trend.append(week_data)

    return {
        "channels": channel_data,
        "total_signups": total_signups,
        "total_clicks": total_clicks,
        "total_revenue": round(total_revenue, 2),
        "best_channel": best_channel,
        "best_channel_label": CHANNEL_META.get(best_channel, {}).get("label", "") if best_channel else "",
        "weekly_trend": weekly_trend,
    }


# ─── Gamification Challenges ───


class CreateChallengeRequest(BaseModel):
    title: str
    description: str
    goal_count: int = Field(ge=1)
    reward_type: str = "credit"  # "credit" or "commission_multiplier"
    reward_value: float = Field(gt=0)
    start_date: str
    end_date: str


async def check_and_update_challenges(user_id: str, event_time: str):
    """Check and update all active challenges for a user after a referral signup."""
    now_str = event_time or datetime.now(timezone.utc).isoformat()

    active_challenges = await db.referral_challenges.find(
        {"is_active": True, "start_date": {"$lte": now_str}, "end_date": {"$gte": now_str}}, {"_id": 0}
    ).to_list(50)

    if not active_challenges:
        return

    for challenge in active_challenges:
        cid = challenge["challenge_id"]

        # Count referrals within the challenge window
        referrals_in_window = await db.referral_events.count_documents(
            {
                "referrer_id": user_id,
                "created_at": {"$gte": challenge["start_date"], "$lte": challenge["end_date"]},
            }
        )

        # Check if already completed
        existing = await db.referral_challenge_progress.find_one({"user_id": user_id, "challenge_id": cid}, {"_id": 0})

        completed = referrals_in_window >= challenge["goal_count"]

        if existing:
            if existing.get("completed"):
                continue  # Already done
            await db.referral_challenge_progress.update_one(
                {"user_id": user_id, "challenge_id": cid},
                {
                    "$set": {
                        "progress": referrals_in_window,
                        "completed": completed,
                        "completed_at": now_str if completed else "",
                    }
                },
            )
        else:
            await db.referral_challenge_progress.insert_one(
                {
                    "user_id": user_id,
                    "challenge_id": cid,
                    "progress": referrals_in_window,
                    "completed": completed,
                    "completed_at": now_str if completed else "",
                    "rewarded": False,
                }
            )

        # Award reward if just completed
        if completed and not (existing or {}).get("completed"):
            if challenge.get("reward_type") == "credit":
                reward_amount = challenge.get("reward_value", 0)
                # Credit the wallet
                wallet = await db.referral_wallets.find_one({"user_id": user_id}, {"_id": 0})
                new_balance = (wallet.get("balance", 0) if wallet else 0) + reward_amount
                await db.referral_wallets.update_one(
                    {"user_id": user_id},
                    {
                        "$inc": {"balance": reward_amount, "total_earned": reward_amount},
                        "$setOnInsert": {"total_applied": 0},
                    },
                    upsert=True,
                )
                await db.referral_credit_transactions.insert_one(
                    {
                        "user_id": user_id,
                        "type": "credit",
                        "amount": reward_amount,
                        "source": "challenge_reward",
                        "details": f"Challenge completed: {challenge['title']}",
                        "balance_after": round(new_balance, 2),
                        "created_at": now_str,
                    }
                )

            await db.referral_challenge_progress.update_one(
                {"user_id": user_id, "challenge_id": cid},
                {"$set": {"rewarded": True}},
            )

            # Notify the user
            from utils.notification_helper import create_notification

            await create_notification(
                user_id=user_id,
                title="Challenge Completed!",
                message=f'You completed "{challenge["title"]}" and earned ${challenge.get("reward_value", 0)} in credits!',
                notif_type="challenge_completed",
                data={"challenge_id": cid, "reward": challenge.get("reward_value", 0)},
            )


@router.get("/my-challenges")
async def my_challenges(request: Request):
    """Get active/completed challenges with the user's progress."""
    user = await require_auth(request)
    uid = user.user_id
    now_str = datetime.now(timezone.utc).isoformat()

    # Get all active + recently ended challenges (last 30 days)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    challenges = (
        await db.referral_challenges.find({"is_active": True, "end_date": {"$gte": cutoff}}, {"_id": 0})
        .sort("end_date", -1)
        .to_list(20)
    )

    result = []
    for ch in challenges:
        cid = ch["challenge_id"]
        is_active = ch["start_date"] <= now_str <= ch["end_date"]
        is_upcoming = now_str < ch["start_date"]

        # Get user progress
        progress_doc = await db.referral_challenge_progress.find_one({"user_id": uid, "challenge_id": cid}, {"_id": 0})

        # If no progress doc yet for an active challenge, count referrals
        if not progress_doc and is_active:
            referrals_in_window = await db.referral_events.count_documents(
                {
                    "referrer_id": uid,
                    "created_at": {"$gte": ch["start_date"], "$lte": ch["end_date"]},
                }
            )
            progress_doc = {
                "progress": referrals_in_window,
                "completed": referrals_in_window >= ch["goal_count"],
                "rewarded": False,
            }

        progress = (progress_doc or {}).get("progress", 0)
        completed = (progress_doc or {}).get("completed", False)
        rewarded = (progress_doc or {}).get("rewarded", False)

        status = (
            "upcoming"
            if is_upcoming
            else ("active" if is_active and not completed else ("completed" if completed else "expired"))
        )

        result.append(
            {
                "challenge_id": cid,
                "title": ch["title"],
                "description": ch["description"],
                "goal_count": ch["goal_count"],
                "reward_type": ch.get("reward_type", "credit"),
                "reward_value": ch.get("reward_value", 0),
                "start_date": ch["start_date"],
                "end_date": ch["end_date"],
                "progress": progress,
                "completed": completed,
                "rewarded": rewarded,
                "status": status,
                "progress_pct": min(round(progress / ch["goal_count"] * 100, 1), 100),
            }
        )

    active = [c for c in result if c["status"] == "active"]
    completed = [c for c in result if c["status"] == "completed"]
    [c for c in result if c["status"] == "expired"]

    return {
        "challenges": result,
        "active_count": len(active),
        "completed_count": len(completed),
        "total_rewards_earned": sum(c["reward_value"] for c in result if c["rewarded"]),
    }


# ─── Admin Challenge Management ───


@router.post("/admin/challenges")
async def create_challenge(request: Request, body: CreateChallengeRequest):
    """Create a new referral challenge."""
    await require_admin(request)

    challenge_id = f"ch_{uuid.uuid4().hex[:10]}"
    now_str = datetime.now(timezone.utc).isoformat()

    doc = {
        "challenge_id": challenge_id,
        "title": body.title,
        "description": body.description,
        "goal_count": body.goal_count,
        "reward_type": body.reward_type,
        "reward_value": body.reward_value,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "is_active": True,
        "created_at": now_str,
    }
    await db.referral_challenges.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "challenge": doc}


@router.put("/admin/challenges/{challenge_id}")
async def update_challenge(request: Request, challenge_id: str):
    """Update or deactivate a challenge."""
    await require_admin(request)
    body = await request.json()

    update_fields = {}
    for field in [
        "title",
        "description",
        "goal_count",
        "reward_type",
        "reward_value",
        "start_date",
        "end_date",
        "is_active",
    ]:
        if field in body:
            update_fields[field] = body[field]

    if not update_fields:
        raise HTTPException(400, "No fields to update")

    result = await db.referral_challenges.update_one({"challenge_id": challenge_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(404, "Challenge not found")

    return {"success": True}


@router.get("/admin/challenges")
async def admin_list_challenges(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all challenges with participation stats."""
    await require_admin(request)

    total_count = await db.referral_challenges.count_documents({})
    skip = (page - 1) * page_size

    challenges = (
        await db.referral_challenges.find({}, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size)
    )

    result = []
    for ch in challenges:
        cid = ch["challenge_id"]
        progress_stats = await db.referral_challenge_progress.aggregate(
            [
                {"$match": {"challenge_id": cid}},
                {
                    "$group": {
                        "_id": None,
                        "participants": {"$sum": 1},
                        "completions": {"$sum": {"$cond": [{"$eq": ["$completed", True]}, 1, 0]}},
                        "rewarded": {"$sum": {"$cond": [{"$eq": ["$rewarded", True]}, 1, 0]}},
                    }
                },
            ]
        ).to_list(1)
        stats = progress_stats[0] if progress_stats else {"participants": 0, "completions": 0, "rewarded": 0}
        participants = int(stats.get("participants", 0) or 0)
        completions = int(stats.get("completions", 0) or 0)
        rewarded_count = int(stats.get("rewarded", 0) or 0)
        total_rewarded = rewarded_count * float(ch.get("reward_value", 0) or 0)

        now_str = datetime.now(timezone.utc).isoformat()
        is_running = ch.get("is_active") and ch["start_date"] <= now_str <= ch["end_date"]

        result.append(
            {
                **ch,
                "participants": participants,
                "completions": completions,
                "total_rewarded": round(total_rewarded, 2),
                "completion_rate": round(completions / participants * 100, 1) if participants > 0 else 0,
                "is_running": is_running,
            }
        )

    return {
        "data": result,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "challenges": result,
    }


@router.get("/admin/challenges/{challenge_id}/participants")
async def admin_challenge_participants(
    request: Request,
    challenge_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Get participants of a specific challenge."""
    await require_admin(request)

    total_count = await db.referral_challenge_progress.count_documents({"challenge_id": challenge_id})
    skip = (page - 1) * page_size

    progress_docs = (
        await db.referral_challenge_progress.find({"challenge_id": challenge_id}, {"_id": 0})
        .sort("progress", -1)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size)
    )

    participants = []
    for p in progress_docs:
        user = await db.users.find_one({"user_id": p["user_id"]}, {"_id": 0, "name": 1, "email": 1, "user_id": 1})
        participants.append(
            {
                "user_id": p["user_id"],
                "name": (user or {}).get("name", "Unknown"),
                "email": (user or {}).get("email", ""),
                "progress": p.get("progress", 0),
                "completed": p.get("completed", False),
                "rewarded": p.get("rewarded", False),
                "completed_at": p.get("completed_at", ""),
            }
        )

    return {
        "data": participants,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "participants": participants,
    }


# ═══════════════════════════════════════════════
# ─── Referral Fraud Detection ─────────────────
# ═══════════════════════════════════════════════

FRAUD_RULES = {
    "rapid_signups": {"threshold": 3, "window_minutes": 60, "severity": "high", "label": "Rapid Signups"},
    "duplicate_ip": {"threshold": 3, "window_hours": 24, "severity": "medium", "label": "Duplicate IP Signups"},
    "zero_conversion": {"threshold": 8, "severity": "low", "label": "Zero Conversion Rate"},
    "self_referral": {"severity": "high", "label": "Self-Referral Attempt"},
    "disposable_email": {"severity": "medium", "label": "Disposable Email Domain"},
    "ip_range_cluster": {"threshold": 5, "severity": "high", "label": "IP Range Cluster"},
    "burst_pattern": {
        "threshold": 3,
        "burst_gap_hours": 2,
        "quiet_hours": 48,
        "severity": "medium",
        "label": "Burst Pattern",
    },
}

LOW_SEVERITY_STALE_ALERT_HOURS = 24


def _build_integrity_alert_suggestion(alert: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    if str(alert.get("status") or "") != "open":
        return None
    if str(alert.get("severity") or "") != "low":
        return None

    created_at_raw = str(alert.get("created_at") or "").strip()
    if not created_at_raw:
        return None

    try:
        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
    except Exception:
        return None

    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    if age_hours < LOW_SEVERITY_STALE_ALERT_HOURS:
        return None

    rule = str(alert.get("rule") or "general").strip().lower()
    total_signups = int(((alert.get("details") or {}).get("total_signups") or 0))
    helper = "Apply the suggestion to close this stale low-severity alert and keep the queue focused on active issues."
    if rule == "zero_conversion" and total_signups > 0:
        helper = f"This zero-conversion alert has been open for over {LOW_SEVERITY_STALE_ALERT_HOURS}h with no escalation. Resolve it as stale and re-run evaluation if signups continue to accumulate."

    return {
        "kind": "stale_low_severity",
        "title": "Auto-resolve suggestion available",
        "action": "resolve_acknowledged",
        "resolution": "auto_resolved_stale_low_severity",
        "reason": f"Open low-severity alert older than {LOW_SEVERITY_STALE_ALERT_HOURS}h",
        "helper": helper,
        "stale_hours": round(age_hours, 1),
    }


def _enrich_integrity_alert(alert: dict[str, Any], now: datetime) -> dict[str, Any]:
    next_alert = dict(alert)
    suggestion = _build_integrity_alert_suggestion(next_alert, now)
    next_alert["suggestion"] = suggestion
    next_alert["has_suggestion"] = bool(suggestion)
    return next_alert


async def _build_integrity_incident_timeline(limit: int = 12) -> list[dict[str, Any]]:
    raw_alerts = (
        await db.referral_integrity_alerts.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    timeline: list[dict[str, Any]] = []
    for idx, alert in enumerate(raw_alerts):
        created_at = _parse_iso_datetime(str(alert.get("created_at") or "")) or datetime.now(timezone.utc)
        window_start = (created_at - timedelta(days=7)).isoformat()
        window_end = created_at.isoformat()

        referral_query: dict[str, Any] = {"created_at": {"$gte": window_start, "$lte": window_end}}
        if "payout_anomaly" in (alert.get("signals") or []):
            referral_query = {
                "$or": [
                    {"created_at": {"$gte": window_start, "$lte": window_end}},
                    {"converted_at": {"$gte": window_start, "$lte": window_end}},
                ]
            }

        event_rows = (
            await db.referral_events.find(
                referral_query,
                {
                    "_id": 0,
                    "referral_id": 1,
                    "referrer_id": 1,
                    "referred_user_id": 1,
                    "status": 1,
                    "plan": 1,
                    "commission_earned": 1,
                    "created_at": 1,
                    "converted_at": 1,
                },
            )
            .sort("created_at", -1)
            .limit(6)
            .to_list(6)
        )

        affected_referral_ids = [str(row.get("referral_id") or "") for row in event_rows if row.get("referral_id")]
        impacted_referrers = sorted({str(row.get("referrer_id") or "") for row in event_rows if row.get("referrer_id")})
        subscribed_count = sum(1 for row in event_rows if str(row.get("status") or "") == "subscribed")
        pending_count = sum(1 for row in event_rows if str(row.get("status") or "") in {"clicked", "signed_up"})
        total_commission = round(sum(float(row.get("commission_earned") or 0) for row in event_rows), 2)

        timeline.append(
            {
                "incident_id": str(alert.get("alert_id") or f"integrity-{idx}"),
                "alert_id": str(alert.get("alert_id") or ""),
                "title": str(alert.get("title") or "Referral Integrity Alert"),
                "status": str(alert.get("status") or "open"),
                "severity": str(alert.get("severity") or "medium"),
                "message": str(alert.get("message") or ""),
                "signals": [str(signal) for signal in (alert.get("signals") or [])],
                "created_at": str(alert.get("created_at") or ""),
                "trigger": str(alert.get("trigger") or "scheduled"),
                "affected_referral_ids": affected_referral_ids,
                "affected_events_count": len(event_rows),
                "impacted_referrers_count": len(impacted_referrers),
                "summary": {
                    "subscribed_count": subscribed_count,
                    "pending_count": pending_count,
                    "commission_at_risk": total_commission,
                },
                "events": [
                    {
                        "referral_id": str(row.get("referral_id") or ""),
                        "referrer_id": str(row.get("referrer_id") or ""),
                        "referred_user_id": str(row.get("referred_user_id") or ""),
                        "status": str(row.get("status") or "pending"),
                        "plan": str(row.get("plan") or "free"),
                        "commission_earned": round(float(row.get("commission_earned") or 0), 2),
                        "created_at": str(row.get("created_at") or ""),
                        "converted_at": str(row.get("converted_at") or ""),
                    }
                    for row in event_rows
                ],
            }
        )

    return timeline

FRAUD_POLICY_PROFILES = {
    "balanced": FRAUD_RULES,
    "strict": {
        **FRAUD_RULES,
        "rapid_signups": {**FRAUD_RULES["rapid_signups"], "threshold": 2},
        "duplicate_ip": {**FRAUD_RULES["duplicate_ip"], "threshold": 2},
        "zero_conversion": {**FRAUD_RULES["zero_conversion"], "threshold": 5},
        "ip_range_cluster": {**FRAUD_RULES["ip_range_cluster"], "threshold": 3},
        "burst_pattern": {
            **FRAUD_RULES["burst_pattern"],
            "threshold": 2,
            "quiet_hours": 24,
        },
    },
}


async def _get_active_fraud_rules() -> dict[str, dict[str, Any]]:
    policy = await db.referral_fraud_policy.find_one({"policy_key": "active"}, {"_id": 0, "rules": 1})
    configured = (policy or {}).get("rules") or {}
    merged = {}
    for key, default_rule in FRAUD_RULES.items():
        merged[key] = {**default_rule, **(configured.get(key) or {})}
    return merged


async def _compute_integrity_metrics(now: datetime) -> dict[str, Any]:
    since_24h = (now - timedelta(hours=24)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()

    open_high = await db.referral_fraud_alerts.count_documents({"status": "open", "severity": "high"})
    open_total = await db.referral_fraud_alerts.count_documents({"status": "open"})

    duplicate_credit_rows = await db.referral_credit_transactions.aggregate(
        [
            {
                "$match": {
                    "type": "credit",
                    "dedupe_key": {"$exists": True, "$nin": [None, ""]},
                    "created_at": {"$gte": since_24h},
                }
            },
            {"$group": {"_id": "$dedupe_key", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "duplicates"},
        ]
    ).to_list(1)
    duplicate_dedupe_keys_24h = int((duplicate_credit_rows[0] if duplicate_credit_rows else {}).get("duplicates") or 0)

    payout_credit_rows = await db.referral_credit_transactions.aggregate(
        [
            {
                "$match": {
                    "type": "credit",
                    "source": "referral_subscription",
                    "created_at": {"$gte": since_24h},
                }
            },
            {"$group": {"_id": None, "sum": {"$sum": "$amount"}}},
        ]
    ).to_list(1)
    payout_credits_24h = float((payout_credit_rows[0] if payout_credit_rows else {}).get("sum") or 0)

    expected_payout_rows = await db.referral_events.aggregate(
        [
            {
                "$match": {
                    "status": "subscribed",
                    "converted_at": {"$gte": since_24h},
                }
            },
            {"$group": {"_id": None, "sum": {"$sum": "$commission_earned"}}},
        ]
    ).to_list(1)
    expected_credits_24h = float((expected_payout_rows[0] if expected_payout_rows else {}).get("sum") or 0)

    recent_signups_7d = await db.referral_events.count_documents({"created_at": {"$gte": since_7d}})
    recent_subscribed_7d = await db.referral_events.count_documents(
        {"status": "subscribed", "converted_at": {"$gte": since_7d}}
    )

    payout_anomaly = payout_credits_24h > (expected_credits_24h * 1.35 + 20)
    return {
        "open_high_alerts": open_high,
        "open_total_alerts": open_total,
        "duplicate_dedupe_keys_24h": duplicate_dedupe_keys_24h,
        "payout_credits_24h": round(payout_credits_24h, 2),
        "expected_credits_24h": round(expected_credits_24h, 2),
        "payout_anomaly": payout_anomaly,
        "recent_signups_7d": recent_signups_7d,
        "recent_subscribed_7d": recent_subscribed_7d,
    }


def _recommend_fraud_profile(metrics: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if int(metrics.get("open_high_alerts") or 0) >= 3:
        reasons.append("high_severity_alert_spike")
    if int(metrics.get("duplicate_dedupe_keys_24h") or 0) >= 1:
        reasons.append("duplicate_credit_key_detected")
    if bool(metrics.get("payout_anomaly")):
        reasons.append("payout_vs_expected_anomaly")

    if reasons:
        profile = "strict"
        confidence = 0.86
    else:
        profile = "balanced"
        confidence = 0.71

    return {
        "recommended_profile": profile,
        "confidence": confidence,
        "reasons": reasons,
        "recommended_rules": FRAUD_POLICY_PROFILES[profile],
    }


async def evaluate_and_emit_referral_integrity_alerts(trigger: str = "scheduled") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    metrics = await _compute_integrity_metrics(now)
    recommendation = _recommend_fraud_profile(metrics)

    anomaly_signals = []
    if int(metrics.get("open_high_alerts") or 0) >= 3:
        anomaly_signals.append("fraud_spike")
    if int(metrics.get("duplicate_dedupe_keys_24h") or 0) >= 1:
        anomaly_signals.append("duplicate_prevention_breach")
    if bool(metrics.get("payout_anomaly")):
        anomaly_signals.append("payout_anomaly")

    if not anomaly_signals:
        return {
            "success": True,
            "alert_generated": False,
            "signals": [],
            "metrics": metrics,
            "recommendation": recommendation,
        }

    fingerprint = hashlib.sha256(
        f"{now.strftime('%Y-%m-%d-%H')}:{','.join(sorted(anomaly_signals))}".encode("utf-8")
    ).hexdigest()
    existing = await db.referral_integrity_alerts.find_one({"fingerprint": fingerprint, "status": "open"}, {"_id": 0})
    if existing:
        return {
            "success": True,
            "alert_generated": False,
            "deduped": True,
            "signals": anomaly_signals,
            "metrics": metrics,
            "recommendation": recommendation,
        }

    alert_id = f"ria_{uuid.uuid4().hex[:10]}"
    title = "Referral Integrity Alert"
    message = (
        f"Signals: {', '.join(anomaly_signals)} · high_open={metrics['open_high_alerts']} · "
        f"dup_keys_24h={metrics['duplicate_dedupe_keys_24h']} · payout_anomaly={metrics['payout_anomaly']}"
    )

    alert_doc = {
        "alert_id": alert_id,
        "fingerprint": fingerprint,
        "severity": "high" if "payout_anomaly" in anomaly_signals else "medium",
        "title": title,
        "message": message,
        "signals": anomaly_signals,
        "metrics": metrics,
        "recommendation": recommendation,
        "trigger": trigger,
        "status": "open",
        "created_at": now.isoformat(),
    }
    await db.referral_integrity_alerts.insert_one(alert_doc)

    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(200)

    from utils.notification_helper import create_notification
    from utils.email_service import send_email, is_email_configured
    from utils.email_templates import _wrap, DASH_URL

    for admin in admins:
        admin_id = str(admin.get("user_id") or "").strip()
        if not admin_id:
            continue
        await create_notification(
            user_id=admin_id,
            title=title,
            message=message,
            notif_type="referral_integrity_alert",
            data={"alert_id": alert_id, "signals": anomaly_signals, "recommended_profile": recommendation["recommended_profile"]},
        )

    if is_email_configured():
        body = (
            f"<p style='margin:0 0 12px;'>Signals detected: <b>{', '.join(anomaly_signals)}</b></p>"
            f"<p style='margin:0 0 8px;'>Open high alerts: <b>{metrics['open_high_alerts']}</b></p>"
            f"<p style='margin:0 0 8px;'>Duplicate dedupe keys (24h): <b>{metrics['duplicate_dedupe_keys_24h']}</b></p>"
            f"<p style='margin:0 0 8px;'>Payout anomaly: <b>{'YES' if metrics['payout_anomaly'] else 'NO'}</b></p>"
            f"<p style='margin:0;'>Recommended profile: <b>{recommendation['recommended_profile']}</b> ({recommendation['confidence']:.2f})</p>"
        )
        html = _wrap(
            "Referral Integrity Alert",
            "Fraud spike / payout anomaly detected",
            body,
            "Open Referral Analytics",
            f"{DASH_URL}/admin-console?tab=referrals",
            "#EF4444",
            category="notifications",
        )
        for admin in admins:
            email = str(admin.get("email") or "").strip()
            if not email:
                continue
            await send_email(email, "[ALERT] Referral Integrity Monitor", html, template_key="system_alert_admin")

    return {
        "success": True,
        "alert_generated": True,
        "alert_id": alert_id,
        "signals": anomaly_signals,
        "metrics": metrics,
        "recommendation": recommendation,
    }

# Common disposable email domains
DISPOSABLE_DOMAINS = {
    "tempmail.com",
    "guerrillamail.com",
    "mailinator.com",
    "throwaway.email",
    "yopmail.com",
    "sharklasers.com",
    "guerrillamailblock.com",
    "grr.la",
    "dispostable.com",
    "maildrop.cc",
    "temp-mail.org",
    "10minutemail.com",
    "fakeinbox.com",
    "trashmail.com",
    "getnada.com",
    "mohmal.com",
    "tempail.com",
    "burnermail.io",
    "tempr.email",
    "harakirimail.com",
    "mailnesia.com",
    "guerrillamail.info",
    "emailondeck.com",
}


async def run_fraud_scan():
    """Scan referral data for suspicious patterns and generate alerts."""
    if not REFERRALS_FRAUD_AUTOSCAN_ENABLED:
        logger.info("Referral fraud scan skipped because REFERRALS_FRAUD_AUTOSCAN_ENABLED is disabled")
        return 0
    await _ensure_referrals_indexes()
    active_rules = await _get_active_fraud_rules()

    now = datetime.now(timezone.utc)
    alerts_generated = 0

    # Rule 1: Rapid signups — a referrer gaining many signups in a short window
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    pipeline_rapid = [
        {"$match": {"created_at": {"$gte": one_hour_ago}}},
        {
            "$group": {
                "_id": "$referrer_id",
                "count": {"$sum": 1},
                "events": {
                    "$push": {"referred_email": "$referred_email", "created_at": "$created_at", "channel": "$channel"}
                },
            }
        },
        {"$match": {"count": {"$gte": active_rules["rapid_signups"]["threshold"]}}},
    ]
    rapid_results = await db.referral_events.aggregate(pipeline_rapid).to_list(100)
    for r in rapid_results:
        alert_key = f"rapid_signups_{r['_id']}_{now.strftime('%Y%m%d%H')}"
        existing = await db.referral_fraud_alerts.find_one({"alert_key": alert_key}, {"_id": 0})
        if not existing:
            user_doc = await db.users.find_one({"user_id": r["_id"]}, {"_id": 0, "name": 1, "email": 1})
            await db.referral_fraud_alerts.insert_one(
                {
                    "alert_id": f"fra_{uuid.uuid4().hex[:10]}",
                    "alert_key": alert_key,
                    "rule": "rapid_signups",
                    "severity": "high",
                    "user_id": r["_id"],
                    "user_name": (user_doc or {}).get("name", "Unknown"),
                    "user_email": (user_doc or {}).get("email", ""),
                    "description": f"{r['count']} referral signups in the last hour",
                    "details": {"count": r["count"], "events": r["events"][:5]},
                    "status": "open",
                    "created_at": now.isoformat(),
                }
            )
            alerts_generated += 1

    # Rule 2: Duplicate IP — multiple signups from the same IP for the same referrer
    twenty_four_hours_ago = (now - timedelta(hours=24)).isoformat()
    pipeline_ip = [
        {"$match": {"clicked_at": {"$gte": twenty_four_hours_ago}, "ip": {"$ne": ""}}},
        {"$group": {"_id": {"referrer_id": "$referrer_id", "ip": "$ip"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gte": active_rules["duplicate_ip"]["threshold"]}}},
    ]
    ip_results = await db.referral_click_log.aggregate(pipeline_ip).to_list(100)
    for r in ip_results:
        rid = r["_id"]["referrer_id"]
        ip = r["_id"]["ip"]
        alert_key = f"dup_ip_{rid}_{ip}_{now.strftime('%Y%m%d')}"
        existing = await db.referral_fraud_alerts.find_one({"alert_key": alert_key}, {"_id": 0})
        if not existing:
            user_doc = await db.users.find_one({"user_id": rid}, {"_id": 0, "name": 1, "email": 1})
            await db.referral_fraud_alerts.insert_one(
                {
                    "alert_id": f"fra_{uuid.uuid4().hex[:10]}",
                    "alert_key": alert_key,
                    "rule": "duplicate_ip",
                    "severity": "medium",
                    "user_id": rid,
                    "user_name": (user_doc or {}).get("name", "Unknown"),
                    "user_email": (user_doc or {}).get("email", ""),
                    "description": f"{r['count']} clicks from IP {ip} in 24h",
                    "details": {"ip": ip, "count": r["count"]},
                    "status": "open",
                    "created_at": now.isoformat(),
                }
            )
            alerts_generated += 1

    # Rule 3: Zero conversion — referrers with many signups but zero subscriptions
    pipeline_conv = [
        {
            "$group": {
                "_id": "$referrer_id",
                "total": {"$sum": 1},
                "subscribed": {"$sum": {"$cond": [{"$eq": ["$status", "subscribed"]}, 1, 0]}},
            }
        },
        {"$match": {"total": {"$gte": active_rules["zero_conversion"]["threshold"]}, "subscribed": 0}},
    ]
    conv_results = await db.referral_events.aggregate(pipeline_conv).to_list(100)
    for r in conv_results:
        alert_key = f"zero_conv_{r['_id']}"
        existing = await db.referral_fraud_alerts.find_one({"alert_key": alert_key, "status": "open"}, {"_id": 0})
        if not existing:
            user_doc = await db.users.find_one({"user_id": r["_id"]}, {"_id": 0, "name": 1, "email": 1})
            await db.referral_fraud_alerts.insert_one(
                {
                    "alert_id": f"fra_{uuid.uuid4().hex[:10]}",
                    "alert_key": alert_key,
                    "rule": "zero_conversion",
                    "severity": "low",
                    "user_id": r["_id"],
                    "user_name": (user_doc or {}).get("name", "Unknown"),
                    "user_email": (user_doc or {}).get("email", ""),
                    "description": f"{r['total']} signups, 0 subscriptions — possible fake referrals",
                    "details": {"total_signups": r["total"]},
                    "status": "open",
                    "created_at": now.isoformat(),
                }
            )
            alerts_generated += 1

    # Rule 4: Disposable email domain detection
    referrer_disposable = {}
    async for e in iter_find_paginated(
        db.referral_events,
        {},
        {"_id": 0, "referrer_id": 1, "referred_email": 1},
        max_docs=5000,
    ):
        email = e.get("referred_email", "")
        domain = email.split("@")[-1].lower() if "@" in email else ""
        if domain in DISPOSABLE_DOMAINS:
            rid = e.get("referrer_id", "")
            referrer_disposable.setdefault(rid, []).append(email)
    for rid, emails in referrer_disposable.items():
        if len(emails) >= 2:
            alert_key = f"disp_email_{rid}"
            existing = await db.referral_fraud_alerts.find_one({"alert_key": alert_key, "status": "open"}, {"_id": 0})
            if not existing:
                user_doc = await db.users.find_one({"user_id": rid}, {"_id": 0, "name": 1, "email": 1})
                await db.referral_fraud_alerts.insert_one(
                    {
                        "alert_id": f"fra_{uuid.uuid4().hex[:10]}",
                        "alert_key": alert_key,
                        "rule": "disposable_email",
                        "severity": "medium",
                        "user_id": rid,
                        "user_name": (user_doc or {}).get("name", "Unknown"),
                        "user_email": (user_doc or {}).get("email", ""),
                        "description": f"{len(emails)} referrals using disposable email domains",
                        "details": {"disposable_emails": emails[:5], "count": len(emails)},
                        "status": "open",
                        "created_at": now.isoformat(),
                    }
                )
                alerts_generated += 1

    # Rule 5: IP range cluster — many signups from similar IP range (same /24 subnet)
    referrer_subnets = {}
    async for c in iter_find_paginated(
        db.referral_click_log,
        {"ip": {"$ne": ""}},
        {"_id": 0, "referrer_id": 1, "ip": 1},
        max_docs=5000,
    ):
        ip = c.get("ip", "")
        parts = ip.split(".")
        if len(parts) == 4:
            subnet = ".".join(parts[:3])
            rid = c.get("referrer_id", "")
            referrer_subnets.setdefault(rid, {}).setdefault(subnet, 0)
            referrer_subnets[rid][subnet] += 1
    for rid, subnets in referrer_subnets.items():
        for subnet, count in subnets.items():
            if count >= active_rules["ip_range_cluster"]["threshold"]:
                alert_key = f"ip_cluster_{rid}_{subnet}"
                existing = await db.referral_fraud_alerts.find_one(
                    {"alert_key": alert_key, "status": "open"}, {"_id": 0}
                )
                if not existing:
                    user_doc = await db.users.find_one({"user_id": rid}, {"_id": 0, "name": 1, "email": 1})
                    await db.referral_fraud_alerts.insert_one(
                        {
                            "alert_id": f"fra_{uuid.uuid4().hex[:10]}",
                            "alert_key": alert_key,
                            "rule": "ip_range_cluster",
                            "severity": "high",
                            "user_id": rid,
                            "user_name": (user_doc or {}).get("name", "Unknown"),
                            "user_email": (user_doc or {}).get("email", ""),
                            "description": f"{count} clicks from IP subnet {subnet}.x — possible bot activity",
                            "details": {"subnet": subnet, "count": count},
                            "status": "open",
                            "created_at": now.isoformat(),
                        }
                    )
                    alerts_generated += 1

    # Rule 6: Burst pattern — referrals arriving in rapid bursts with long quiet gaps
    referrer_events = {}
    async for e in iter_find_paginated(
        db.referral_events,
        {},
        {"_id": 0, "referrer_id": 1, "created_at": 1},
        sort=[("created_at", 1)],
        max_docs=5000,
    ):
        rid = e.get("referrer_id", "")
        ts = e.get("created_at", "")
        referrer_events.setdefault(rid, []).append(ts)
    burst_thresh = active_rules["burst_pattern"]["threshold"]
    burst_gap = active_rules["burst_pattern"]["burst_gap_hours"]
    quiet_hours = active_rules["burst_pattern"]["quiet_hours"]
    for rid, timestamps in referrer_events.items():
        if len(timestamps) < burst_thresh * 2:
            continue
        bursts = []
        current_burst = [timestamps[0]]
        for i in range(1, len(timestamps)):
            try:
                t1 = datetime.fromisoformat(timestamps[i - 1].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
                gap = (t2 - t1).total_seconds() / 3600
                if gap <= burst_gap:
                    current_burst.append(timestamps[i])
                else:
                    if len(current_burst) >= burst_thresh:
                        bursts.append({"count": len(current_burst), "gap_before_hours": gap})
                    current_burst = [timestamps[i]]
            except Exception:
                current_burst = [timestamps[i]]
        if len(current_burst) >= burst_thresh:
            bursts.append({"count": len(current_burst), "gap_before_hours": 0})
        suspicious_bursts = [b for b in bursts if b.get("gap_before_hours", 0) >= quiet_hours]
        if len(suspicious_bursts) >= 2:
            alert_key = f"burst_{rid}"
            existing = await db.referral_fraud_alerts.find_one({"alert_key": alert_key, "status": "open"}, {"_id": 0})
            if not existing:
                user_doc = await db.users.find_one({"user_id": rid}, {"_id": 0, "name": 1, "email": 1})
                await db.referral_fraud_alerts.insert_one(
                    {
                        "alert_id": f"fra_{uuid.uuid4().hex[:10]}",
                        "alert_key": alert_key,
                        "rule": "burst_pattern",
                        "severity": "medium",
                        "user_id": rid,
                        "user_name": (user_doc or {}).get("name", "Unknown"),
                        "user_email": (user_doc or {}).get("email", ""),
                        "description": f"{len(suspicious_bursts)} referral bursts with {quiet_hours}h+ quiet gaps — bot-like timing",
                        "details": {"bursts": suspicious_bursts[:5], "total_bursts": len(suspicious_bursts)},
                        "status": "open",
                        "created_at": now.isoformat(),
                    }
                )
                alerts_generated += 1

    return alerts_generated


@router.get("/admin/fraud-alerts")
async def admin_fraud_alerts(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    """Get referral fraud detection alerts with summary stats."""
    await require_admin(request)

    latest_scan = await db.referral_fraud_scan_history.find_one({}, {"_id": 0}, sort=[("scan_time", -1)])

    total_count = await db.referral_fraud_alerts.count_documents({})
    total_open = await db.referral_fraud_alerts.count_documents({"status": "open"})
    total_resolved = await db.referral_fraud_alerts.count_documents({"status": "resolved"})
    skip = (page - 1) * page_size

    alerts = (
        await db.referral_fraud_alerts.find({}, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
        .to_list(page_size)
    )

    severity_counts = {"high": 0, "medium": 0, "low": 0}
    severity_rows = await db.referral_fraud_alerts.aggregate(
        [
            {"$match": {"status": "open"}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
    ).to_list(10)
    for row in severity_rows:
        sev = str(row.get("_id") or "low")
        severity_counts[sev] = int(row.get("count", 0) or 0)

    rule_counts = {}
    rule_rows = await db.referral_fraud_alerts.aggregate(
        [
            {"$match": {"status": "open"}},
            {"$group": {"_id": "$rule", "count": {"$sum": 1}}},
        ]
    ).to_list(50)
    for row in rule_rows:
        rule = str(row.get("_id") or "unknown")
        rule_counts[rule] = int(row.get("count", 0) or 0)

    return {
        "data": alerts,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "alerts": alerts,
        "total_open": total_open,
        "total_resolved": total_resolved,
        "severity_counts": severity_counts,
        "rule_counts": rule_counts,
        "new_alerts_found": 0,
        "rules": FRAUD_RULES,
        "last_scan": str((latest_scan or {}).get("scan_time") or ""),
        "last_scan_type": str((latest_scan or {}).get("scan_type") or ""),
        "last_scan_new_alerts": int((latest_scan or {}).get("alerts_generated") or 0),
        "scan_history": await db.referral_fraud_scan_history.find({}, {"_id": 0}).sort("scan_time", -1).to_list(10),
        "schedule": {"interval_hours": 6, "next_scan": "Automated every 6 hours"},
    }


@router.post("/admin/fraud-scan/run")
async def manual_fraud_scan(request: Request):
    """Manually trigger a fraud scan."""
    admin_user = await require_admin(request)
    _assert_rate_limit(
        request,
        "manual_fraud_scan",
        limit=5,
        window_seconds=300,
        actor_hint=str(getattr(admin_user, "user_id", "admin")),
    )
    if not REFERRALS_FRAUD_AUTOSCAN_ENABLED:
        return {
            "success": False,
            "new_alerts": 0,
            "message": "Fraud scan is temporarily disabled by platform policy.",
            "error_code": "referral_fraud_scan_disabled",
        }
    new_alerts = await run_fraud_scan()
    integrity_result = await evaluate_and_emit_referral_integrity_alerts(trigger="manual_fraud_scan")
    await db.referral_fraud_scan_history.insert_one(
        {
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "alerts_generated": new_alerts,
            "scan_type": "manual",
        }
    )
    return {
        "success": True,
        "new_alerts": new_alerts,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "integrity_alert": integrity_result,
    }


@router.post("/admin/fraud-alerts/{alert_id}/resolve")
async def resolve_fraud_alert(request: Request, alert_id: str):
    """Mark a fraud alert as resolved."""
    await require_admin(request)
    body = await request.json()
    resolution = body.get("resolution", "dismissed")

    result = await db.referral_fraud_alerts.update_one(
        {"alert_id": alert_id},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Alert not found")

    return {"success": True, "alert_id": alert_id}


@router.post("/admin/fraud-alerts/{alert_id}/block")
async def block_referrer(request: Request, alert_id: str):
    """Block a referrer flagged by fraud detection."""
    await require_admin(request)

    alert = await db.referral_fraud_alerts.find_one({"alert_id": alert_id}, {"_id": 0})
    if not alert:
        raise HTTPException(404, "Alert not found")

    user_id = alert.get("user_id")
    await db.referral_codes.update_one(
        {"user_id": user_id}, {"$set": {"blocked": True, "blocked_at": datetime.now(timezone.utc).isoformat()}}
    )
    await db.referral_fraud_alerts.update_one(
        {"alert_id": alert_id},
        {
            "$set": {
                "status": "resolved",
                "resolution": "user_blocked",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    return {"success": True, "user_id": user_id, "action": "blocked"}


# ═══════════════════════════════════════════════
# ─── Social Proof & Leaderboard Enhancements ──
# ═══════════════════════════════════════════════


@router.get("/recent-activity")
async def recent_referral_activity(request: Request):
    """Public endpoint for social proof — recent anonymized referral activity."""
    # No auth required for social proof
    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    recent_events = (
        await db.referral_events.find(
            {"created_at": {"$gte": seven_days_ago}},
            {"_id": 0, "referrer_id": 1, "referred_name": 1, "status": 1, "created_at": 1, "channel": 1, "plan": 1},
        )
        .sort("created_at", -1)
        .to_list(20)
    )

    activity = []
    for e in recent_events:
        name = e.get("referred_name", "Someone")
        anon_name = name[0] + "***" if name and len(name) > 1 else "Someone"
        elapsed = (
            (now - datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))).total_seconds()
            if e.get("created_at")
            else 0
        )
        if elapsed < 3600:
            time_ago = f"{int(elapsed // 60)}m ago"
        elif elapsed < 86400:
            time_ago = f"{int(elapsed // 3600)}h ago"
        else:
            time_ago = f"{int(elapsed // 86400)}d ago"

        status = e.get("status", "signed_up")
        action = "joined" if status == "signed_up" else ("subscribed" if status == "subscribed" else "joined")
        activity.append(
            {
                "name": anon_name,
                "action": action,
                "plan": e.get("plan", "free") if status == "subscribed" else None,
                "channel": e.get("channel", "direct"),
                "time_ago": time_ago,
            }
        )

    # Platform stats for social proof banner
    total_referrers = await db.referral_codes.count_documents({"total_signups": {"$gt": 0}})
    total_signups = await db.referral_events.count_documents({})
    week_signups = await db.referral_events.count_documents({"created_at": {"$gte": seven_days_ago}})

    return {
        "activity": activity,
        "stats": {
            "total_referrers": total_referrers,
            "total_signups": total_signups,
            "this_week_signups": week_signups,
        },
    }


@router.get("/leaderboard-highlights")
async def leaderboard_highlights(request: Request):
    """Enhanced leaderboard data with highlights: top mover, streaks, new entrants."""
    user = None
    try:
        user = await require_auth(request)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    # Get all referral codes
    all_codes = (
        await db.referral_codes.find(
            {"total_signups": {"$gt": 0}},
            {"_id": 0, "user_id": 1, "code": 1, "total_signups": 1, "total_clicks": 1, "name": 1, "created_at": 1},
        )
        .sort("total_signups", -1)
        .to_list(50)
    )

    # Get recent events per referrer for "Top Mover" detection
    weekly_counts = {}
    async for e in iter_find_paginated(
        db.referral_events,
        {"created_at": {"$gte": seven_days_ago}},
        {"_id": 0, "referrer_id": 1},
        max_docs=5000,
    ):
        rid = e.get("referrer_id", "")
        weekly_counts[rid] = weekly_counts.get(rid, 0) + 1

    # Build leaderboard
    leaderboard = []
    top_mover_id = None
    top_mover_weekly = 0
    for i, c in enumerate(all_codes):
        uid = c["user_id"]
        signups = c.get("total_signups", 0)
        tier = _get_tier(signups)
        weekly = weekly_counts.get(uid, 0)
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1})
        full_name = (u or {}).get("name", "Anonymous")
        is_self = user and user.user_id == uid
        display_name = full_name if is_self else _anonymize(full_name)

        # Detect new entrant (joined in last 30 days)
        is_new = c.get("created_at", "") >= thirty_days_ago if c.get("created_at") else False

        entry = {
            "rank": i + 1,
            "display_name": display_name,
            "is_self": bool(is_self),
            "total_signups": signups,
            "total_clicks": c.get("total_clicks", 0),
            "weekly_signups": weekly,
            "tier": {"id": tier["id"], "name": tier["name"], "color": tier["color"], "commission": tier["commission"]},
            "badges": [],
            "is_new_entrant": is_new,
        }

        # Assign badges
        if weekly > 0 and weekly > top_mover_weekly:
            top_mover_weekly = weekly
            top_mover_id = uid
        if signups >= 50:
            entry["badges"].append({"id": "legend", "label": "Legend", "color": "#FFD700", "icon": "trophy"})
        if signups >= 25:
            entry["badges"].append({"id": "ambassador", "label": "Ambassador", "color": "#8B5CF6", "icon": "diamond"})
        if is_new:
            entry["badges"].append({"id": "newcomer", "label": "New", "color": "#10B981", "icon": "sparkles"})
        if weekly >= 3:
            entry["badges"].append({"id": "hot_streak", "label": "On Fire", "color": "#EF4444", "icon": "flame"})

        leaderboard.append(entry)

    # Mark top mover
    if top_mover_id and top_mover_weekly > 0:
        for j, entry in enumerate(leaderboard):
            if j < len(all_codes) and all_codes[j]["user_id"] == top_mover_id:
                entry["badges"].insert(
                    0, {"id": "top_mover", "label": "Top Mover", "color": "#F59E0B", "icon": "trending-up"}
                )
                entry["is_top_mover"] = True
                break

    # My position
    my_position = None
    if user:
        my_code = await db.referral_codes.find_one({"user_id": user.user_id}, {"_id": 0, "total_signups": 1, "code": 1})
        if my_code:
            my_signups = my_code.get("total_signups", 0)
            higher = await db.referral_codes.count_documents({"total_signups": {"$gt": my_signups}})
            my_tier = _get_tier(my_signups)
            my_weekly = weekly_counts.get(user.user_id, 0)
            my_position = {
                "rank": higher + 1,
                "total_signups": my_signups,
                "weekly_signups": my_weekly,
                "tier": {"id": my_tier["id"], "name": my_tier["name"], "color": my_tier["color"]},
                "in_top_50": any(e.get("is_self") for e in leaderboard),
            }

    return {
        "leaderboard": leaderboard,
        "total_participants": await db.referral_codes.count_documents({}),
        "my_position": my_position,
        "tiers": TIERS,
        "highlights": {
            "top_mover_weekly": top_mover_weekly,
            "new_entrants_count": sum(1 for e in leaderboard if e.get("is_new_entrant")),
            "active_this_week": len(weekly_counts),
        },
    }
