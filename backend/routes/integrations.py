"""3rd party integrations: Weather, Finance, Crypto, Calendar, Image Gen."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, RedirectResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode
import httpx
import os
import uuid
import base64
import asyncio
import calendar as pycalendar
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from .db import db, EMERGENT_LLM_KEY, logger, get_current_user, require_admin
from utils.ws_manager import ws_manager
from utils.access_control_engine import compute_effective_plan


async def _create_and_push_notification(notif: dict):
    """Insert notification into DB and push via WebSocket."""
    await db.notifications.insert_one(notif)
    notif.pop("_id", None)
    try:
        unread = await db.notifications.count_documents({"user_id": notif["user_id"], "read": False})
        await ws_manager.send_to_user(
            notif["user_id"],
            {
                "type": "notification",
                "notification": notif,
                "unread_count": unread,
            },
        )
    except Exception as e:
        logger.error(f"WS push failed: {e}")


from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration

load_dotenv()
router = APIRouter()


# ── Crypto (CoinGecko - free) ──
@router.get("/data/crypto")
async def get_crypto_data(coins: str = "bitcoin,ethereum,solana", currency: str = "usd"):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": coins,
                    "vs_currencies": currency,
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                },
                timeout=10,
            )
            return (
                {"data": resp.json(), "source": "coingecko", "currency": currency}
                if resp.status_code == 200
                else {"data": {}, "error": "CoinGecko API unavailable"}
            )
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return {"data": {}, "error": "Failed to fetch crypto data"}


# ── Weather (Open-Meteo - free) ──
@router.get("/data/weather")
async def get_weather_data(lat: float = 40.7128, lon: float = -74.0060):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                    "forecast_days": 7,
                    "timezone": "auto",
                },
                timeout=10,
            )
            return (
                {"data": resp.json(), "source": "open-meteo"}
                if resp.status_code == 200
                else {"data": {}, "error": "Weather API unavailable"}
            )
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return {"data": {}, "error": "Failed to fetch weather data"}


# ── Finance (Alpha Vantage - free demo) ──
@router.get("/data/finance")
async def get_finance_data(symbol: str = "AAPL"):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": "demo"},
                timeout=10,
            )
            if resp.status_code == 200:
                quote = resp.json().get("Global Quote", {})
                return {
                    "symbol": quote.get("01. symbol", symbol),
                    "price": quote.get("05. price", "N/A"),
                    "change": quote.get("09. change", "N/A"),
                    "change_percent": quote.get("10. change percent", "N/A"),
                    "volume": quote.get("06. volume", "N/A"),
                    "source": "alphavantage",
                }
            return {"symbol": symbol, "error": "Finance API unavailable"}
    except Exception as e:
        logger.error(f"Alpha Vantage error: {e}")
        return {"symbol": symbol, "error": "Failed to fetch finance data"}


# ── Calendar (Google + local) ──
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_OAUTH_STATE_TTL_MINUTES = 15


def is_google_calendar_configured() -> bool:
    return all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET])


def _get_google_redirect_uri(request: Request = None) -> str:
    """Compute the OAuth redirect URI dynamically from the request or env."""
    if request:
        # Derive from the incoming request for correct domain
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        scheme = request.headers.get("x-forwarded-proto") or "https"
        if host:
            return f"{scheme}://{host}/api/oauth/calendar/callback"
    # Fallback to env
    return os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "")


def _build_google_auth_url(state: str, request: Request = None) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": _get_google_redirect_uri(request),
        "response_type": "code",
        "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"


def _normalize_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_calendar_state_expired(state_doc: Dict[str, Any]) -> bool:
    now = datetime.now(timezone.utc)
    expires_at = _normalize_dt(state_doc.get("expires_at"))
    if expires_at:
        return expires_at <= now

    created_at = _normalize_dt(state_doc.get("created_at"))
    if not created_at:
        return True
    return created_at <= (now - timedelta(minutes=CALENDAR_OAUTH_STATE_TTL_MINUTES))


async def _create_calendar_oauth_state(user_id: str) -> str:
    state = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    await db.calendar_oauth_states.insert_one(
        {
            "state": state,
            "user_id": user_id,
            "created_at": now,
            "expires_at": now + timedelta(minutes=CALENDAR_OAUTH_STATE_TTL_MINUTES),
        }
    )
    await db.calendar_oauth_states.create_index("expires_at", expireAfterSeconds=0)
    return state


def _format_event_time(value: str) -> Dict[str, str]:
    if not value:
        return {}
    if len(value) == 10 and "-" in value:
        return {"date": value}
    return {"dateTime": value, "timeZone": "UTC"}


def _build_reminders(reminders: Optional[Dict[str, Any]], reminder_minutes: Optional[int]) -> Optional[Dict[str, Any]]:
    if reminders:
        return reminders
    if reminder_minutes is None:
        return None
    return {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": int(reminder_minutes)}],
    }


def _combine_description(description: str, notes: str) -> str:
    parts = []
    if description:
        parts.append(description)
    if notes:
        parts.append(f"Notes: {notes}")
    return "\n\n".join(parts)


def _subscription_required_payload(current_plan: str, required_plan: str = "basic") -> Dict[str, str]:
    from utils.preprod_entitlement_lock import is_preprod_lock_active

    payload = {
        "error": "Subscription Required",
        "message": f"This feature requires a {required_plan.capitalize()} plan or higher. Upgrade now to unlock access.",
        "current_plan": str(current_plan or "free").lower(),
        "required_plan": str(required_plan or "basic").lower(),
        "upgrade_url": "/subscription/plans",
    }
    if is_preprod_lock_active():
        payload["message"] = "Subscriptions are disabled until production launch."
        payload["detail"] = "Subscriptions are disabled until production launch."
    return payload


def _plan_rank(plan: str) -> int:
    return {"free": 0, "basic": 1, "premium": 2}.get(str(plan or "free").lower(), 0)


async def _enforce_calendar_min_plan(user_id: str, required_plan: str = "free") -> Dict[str, Any]:
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "user_id": 1,
            "is_admin": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "payment_verified": 1,
            "pending_subscription_transition": 1,
            "google_calendar": 1,
            "timezone": 1,
        },
    )
    effective_plan = compute_effective_plan(user_doc or {})
    if _plan_rank(effective_plan) < _plan_rank(required_plan):
        raise HTTPException(status_code=403, detail=_subscription_required_payload(effective_plan, required_plan))
    return user_doc or {}


async def _require_calendar_user(request: Request, required_plan: str = "free"):
    # POLICY 2026-06.v3: My Agenda (#34) is open to Free with limited access.
    # Daily action limits are auto-enforced by the platform entitlement meter.
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await _enforce_calendar_min_plan(user.user_id, required_plan)
    return user


def _assert_user_scope(user_id: str, resource_user_id: str):
    if user_id != resource_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _parse_calendar_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid datetime format") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _validate_event_window(start: str, end: str):
    start_dt = _parse_calendar_dt(start)
    end_dt = _parse_calendar_dt(end)
    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="Event end time must be after start time")
    if (end_dt - start_dt) > timedelta(hours=24):
        raise HTTPException(status_code=400, detail="Event duration exceeds the 24-hour maximum")


def _normalize_recurrence(value: Optional[str]) -> str:
    recurrence = str(value or "none").strip().lower()
    if recurrence not in {"none", "daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="Invalid recurrence value")
    return recurrence


def _add_months_preserving_day(start_dt: datetime, months: int) -> datetime:
    month_index = (start_dt.month - 1) + months
    year = start_dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_dt.day, pycalendar.monthrange(year, month)[1])
    return start_dt.replace(year=year, month=month, day=day)


def _next_half_hour(dt: datetime) -> datetime:
    aligned = dt.replace(second=0, microsecond=0)
    minute = aligned.minute
    if minute in (0, 30):
        return aligned
    if minute < 30:
        return aligned.replace(minute=30)
    return (aligned + timedelta(hours=1)).replace(minute=0)


def _overlaps_busy(start_dt: datetime, end_dt: datetime, busy_ranges: list[tuple[datetime, datetime]]) -> bool:
    for busy_start, busy_end in busy_ranges:
        if start_dt < busy_end and end_dt > busy_start:
            return True
    return False


def _score_slot(
    start_dt: datetime,
    end_dt: datetime,
    now: datetime,
    preferred_hour: int,
    busy_ranges: list[tuple[datetime, datetime]],
    plan_scope: str,
    acceptance_ratio_30d: float,
) -> int:
    score = 50
    normalized_plan = str(plan_scope or "free").lower()

    # Weekday preference
    if start_dt.weekday() < 5:
        score += 14
    else:
        score += 4

    # Favor upcoming near-term windows (but not immediate pressure)
    hours_ahead = (start_dt - now).total_seconds() / 3600
    if 12 <= hours_ahead <= 72:
        score += 18
    elif 4 <= hours_ahead < 12:
        score += 6
    elif hours_ahead < 2:
        score -= 24

    # Plan-aware tuning
    if normalized_plan == "premium":
        if 8 <= hours_ahead <= 48:
            score += 8
    elif normalized_plan == "basic":
        if 10 <= hours_ahead <= 60:
            score += 4

    # Rhythm matching to user's historical meeting start hour
    score += max(0, 16 - (abs(start_dt.hour - preferred_hour) * 3))

    # Behavior tuning from historical acceptance ratio
    if acceptance_ratio_30d >= 0.7:
        score += 6
    elif acceptance_ratio_30d >= 0.4:
        score += 3
    else:
        score -= 2

    # Avoid lunch + late hours slightly
    if start_dt.hour in {12, 13}:
        score -= 4
    if start_dt.hour >= 18:
        score -= 6

    # Bonus for slots surrounded by less density (+/-90m neighborhood)
    neighborhood_start = start_dt - timedelta(minutes=90)
    neighborhood_end = end_dt + timedelta(minutes=90)
    nearby = 0
    for busy_start, busy_end in busy_ranges:
        if neighborhood_start < busy_end and neighborhood_end > busy_start:
            nearby += 1
    if nearby == 0:
        score += 12
    elif nearby == 1:
        score += 5
    else:
        score -= min(14, nearby * 3)

    return max(0, min(100, int(score)))


async def _recommend_best_slot_for_user(user_id: str, duration_minutes: int, category: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    scan_start = now - timedelta(days=21)
    scan_end = now + timedelta(days=7)

    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    effective_plan = compute_effective_plan(user_doc or {})

    telemetry_last_30d = (
        await db.calendar_best_slot_telemetry.find(
            {
                "user_id": user_id,
                "created_at": {"$gte": (now - timedelta(days=30)).isoformat()},
                "action": {"$in": ["accepted", "ignored", "recomputed"]},
            },
            {"_id": 0, "action": 1},
        ).to_list(400)
    )
    accepted_count = sum(1 for item in telemetry_last_30d if str(item.get("action") or "") == "accepted")
    ignored_count = sum(1 for item in telemetry_last_30d if str(item.get("action") or "") == "ignored")
    recomputed_count = sum(1 for item in telemetry_last_30d if str(item.get("action") or "") == "recomputed")
    telemetry_total = max(1, len(telemetry_last_30d))
    acceptance_ratio_30d = accepted_count / telemetry_total

    events = (
        await db.calendar_events.find(
            {
                "user_id": user_id,
                "start": {"$gte": scan_start.isoformat(), "$lte": scan_end.isoformat()},
            },
            {"_id": 0, "start": 1, "end": 1},
        )
        .sort("start", 1)
        .to_list(500)
    )

    busy_ranges: list[tuple[datetime, datetime]] = []
    hour_frequency: Dict[int, int] = {}
    for event in events:
        try:
            start_dt = _parse_calendar_dt(event.get("start", ""))
            end_dt = _parse_calendar_dt(event.get("end", ""))
            if end_dt <= start_dt:
                continue
            busy_ranges.append((start_dt, end_dt))
            if start_dt < now:
                hour_frequency[start_dt.hour] = hour_frequency.get(start_dt.hour, 0) + 1
        except Exception:
            continue

    preferred_hour = 10
    if hour_frequency:
        preferred_hour = sorted(hour_frequency.items(), key=lambda item: item[1], reverse=True)[0][0]

    duration_delta = timedelta(minutes=duration_minutes)
    candidates: list[Dict[str, Any]] = []

    for day_offset in range(0, 8):
        day = now + timedelta(days=day_offset)
        weekday = day.weekday()
        day_start_hour = 8 if weekday < 5 else 10
        day_end_hour = 19 if weekday < 5 else 17

        cursor = datetime(day.year, day.month, day.day, day_start_hour, 0, tzinfo=timezone.utc)
        cursor = _next_half_hour(cursor)
        day_end = datetime(day.year, day.month, day.day, day_end_hour, 0, tzinfo=timezone.utc)

        while cursor + duration_delta <= day_end:
            slot_start = cursor
            slot_end = slot_start + duration_delta
            if slot_start < now + timedelta(minutes=30):
                cursor += timedelta(minutes=30)
                continue
            if _overlaps_busy(slot_start, slot_end, busy_ranges):
                cursor += timedelta(minutes=30)
                continue

            score = _score_slot(
                slot_start,
                slot_end,
                now,
                preferred_hour,
                busy_ranges,
                effective_plan,
                acceptance_ratio_30d,
            )
            candidates.append(
                {
                    "start": slot_start,
                    "end": slot_end,
                    "score": score,
                }
            )
            cursor += timedelta(minutes=30)

    if not candidates:
        fallback_start = _next_half_hour(now + timedelta(hours=2))
        fallback_end = fallback_start + duration_delta
        recommendation = {
            "title": f"{category.capitalize()} Session",
            "start": fallback_start.isoformat(),
            "end": fallback_end.isoformat(),
            "reason": "Earliest available fallback slot based on your current calendar window.",
            "confidence": 52,
            "category": category,
            "duration_minutes": duration_minutes,
            "source": "heuristic-fallback",
            "plan_scope": effective_plan,
            "acceptance_ratio_30d": round(acceptance_ratio_30d, 3),
        }
        return {
            "recommendation": recommendation,
            "alternatives": [],
            "meta": {
                "candidate_count": 0,
                "preferred_hour": preferred_hour,
                "source": "heuristic-fallback",
                "plan_scope": effective_plan,
                "acceptance_ratio_30d": round(acceptance_ratio_30d, 3),
                "behavior_counts_30d": {
                    "accepted": int(accepted_count),
                    "ignored": int(ignored_count),
                    "recomputed": int(recomputed_count),
                },
            },
        }

    ranked = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
    top = ranked[0]
    alternatives = ranked[1:4]

    recommendation = {
        "title": f"{category.capitalize()} Session",
        "start": top["start"].isoformat(),
        "end": top["end"].isoformat(),
        "reason": (
            "Low-conflict window aligned with your scheduling rhythm "
            f"(around {preferred_hour:02d}:00) and near-term execution capacity."
        ),
        "confidence": int(top.get("score", 0)),
        "category": category,
        "duration_minutes": duration_minutes,
        "source": "heuristic",
        "plan_scope": effective_plan,
        "acceptance_ratio_30d": round(acceptance_ratio_30d, 3),
    }

    alt_payload = [
        {
            "start": option["start"].isoformat(),
            "end": option["end"].isoformat(),
            "confidence": int(option.get("score", 0)),
        }
        for option in alternatives
    ]

    return {
        "recommendation": recommendation,
        "alternatives": alt_payload,
        "meta": {
            "candidate_count": len(ranked),
            "preferred_hour": preferred_hour,
            "source": "heuristic",
            "plan_scope": effective_plan,
            "acceptance_ratio_30d": round(acceptance_ratio_30d, 3),
            "behavior_counts_30d": {
                "accepted": int(accepted_count),
                "ignored": int(ignored_count),
                "recomputed": int(recomputed_count),
            },
        },
    }


def _normalize_best_slot_action(action: str) -> str:
    normalized = str(action or "").strip().lower()
    if normalized not in {"accepted", "ignored", "recomputed"}:
        raise HTTPException(status_code=400, detail="Invalid best-slot telemetry action")
    return normalized


def _best_slot_recommendation_snapshot(recommendation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    rec = recommendation or {}
    return {
        "title": str(rec.get("title") or "")[:140],
        "start": str(rec.get("start") or "")[:40],
        "end": str(rec.get("end") or "")[:40],
        "category": str(rec.get("category") or "meeting")[:40],
        "confidence": int(rec.get("confidence") or 0),
        "source": str(rec.get("source") or "")[:60],
    }


async def _record_best_slot_telemetry(
    user_id: str,
    action: str,
    plan_scope: str,
    recommendation: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    telemetry = {
        "id": f"bst_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "action": _normalize_best_slot_action(action),
        "plan_scope": str(plan_scope or "free").lower(),
        "recommendation": _best_slot_recommendation_snapshot(recommendation),
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calendar_best_slot_telemetry.insert_one({**telemetry})
    return telemetry


def _build_weekly_best_slot_reward_badge(
    *,
    plan_scope: str,
    accepted_this_week: int,
    accepted_commit: int,
    accepted_prefill: int,
    accepted_legacy: int,
    now: datetime,
) -> Dict[str, Any]:
    target_accepts = 3
    accepted = max(0, int(accepted_this_week))
    remaining = max(0, target_accepts - accepted)
    progress_ratio = round(min(1.0, accepted / float(target_accepts)), 4)
    earned = accepted >= target_accepts
    normalized_plan = str(plan_scope or "free").strip().lower()

    premium_conversion_nudge = normalized_plan == "basic"
    cta = {
        "label": "Open control ops",
        "intent": "focus",
        "url": "/book-meeting",
    }
    if premium_conversion_nudge:
        cta = {
            "label": "Explore Premium",
            "intent": "upgrade",
            "url": "/subscription/plans",
        }

    return {
        "key": "best_slot_weekly_acceptance_reward",
        "title": "Accept 3 best slots/week",
        "subtitle": "Weekly execution reward",
        "status_label": "UNLOCKED" if earned else f"{accepted}/{target_accepts} accepted",
        "target_accepts_per_week": target_accepts,
        "accepted_this_week": accepted,
        "remaining_to_unlock": remaining,
        "progress_ratio": progress_ratio,
        "earned": earned,
        "tier": "gold" if earned else "progress",
        "window_days": 7,
        "window_started_at": (now - timedelta(days=7)).isoformat(),
        "window_ended_at": now.isoformat(),
        "plan_scope": normalized_plan,
        "premium_conversion_nudge": premium_conversion_nudge,
        "support_copy": (
            "Badge unlocked. Keep committing best slots to preserve your streak momentum."
            if earned
            else f"Accept {remaining} more best-slot recommendation{'s' if remaining != 1 else ''} this week to unlock your reward badge."
        ),
        "telemetry_breakdown": {
            "accepted_commit": max(0, int(accepted_commit)),
            "accepted_prefill": max(0, int(accepted_prefill)),
            "accepted_legacy": max(0, int(accepted_legacy)),
        },
        "cta": cta,
    }


async def _send_calendar_disconnect_alert(user_id: str):
    """Send a one-per-24h alert when Google Calendar token refresh fails."""
    try:
        user_doc = await db.users.find_one(
            {"user_id": user_id},
            {"_id": 0, "email": 1, "name": 1, "google_calendar.disconnect_alert_sent_at": 1},
        )
        if not user_doc:
            return

        # Throttle: max one alert per 24 hours
        last_alert = (user_doc.get("google_calendar") or {}).get("disconnect_alert_sent_at")
        if last_alert:
            try:
                last_dt = datetime.fromisoformat(last_alert)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last_dt).total_seconds() < 86400:
                    return
            except Exception:
                pass

        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"google_calendar.disconnect_alert_sent_at": datetime.now(timezone.utc).isoformat()}},
        )

        from utils.notification_helper import create_notification_for_email

        await create_notification_for_email(
            user_id,
            user_doc.get("email", ""),
            "Google Calendar Disconnected",
            "Your Google Calendar connection was lost. Please reconnect from the Calendar page to keep your events in sync.",
            "calendar_disconnected",
        )
        logger.info(f"Sent Google Calendar disconnect alert to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send calendar disconnect alert for {user_id}: {e}")



async def _get_google_credentials(user_id: str) -> Optional[Credentials]:
    if not is_google_calendar_configured():
        return None
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    tokens = user_doc.get("google_calendar") if user_doc else None
    if not tokens:
        return None

    expiry = None
    if tokens.get("expires_at"):
        try:
            expiry = datetime.fromisoformat(tokens["expires_at"])
            # Google auth library uses naive UTC datetimes internally,
            # so we must strip tzinfo to avoid comparison errors.
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except Exception:
            expiry = None

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=GOOGLE_CALENDAR_SCOPES,
        expiry=expiry,
    )

    try:
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            await db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "google_calendar.access_token": creds.token,
                        "google_calendar.expires_at": creds.expiry.isoformat() if creds.expiry else None,
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$unset": {"google_calendar.disconnect_alert_sent_at": ""},
                },
            )
    except Exception as e:
        logger.warning(f"Google Calendar token refresh failed for user {user_id}: {e}")
        asyncio.ensure_future(_send_calendar_disconnect_alert(user_id))
        return None
    return creds


async def _get_google_service(user_id: str):
    creds = await _get_google_credentials(user_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)


async def _get_selected_calendar_id(user_id: str) -> str:
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    calendar_id = (user_doc or {}).get("google_calendar", {}).get("calendar_id")
    return calendar_id or "primary"


async def _sync_google_events(user_id: str, calendar_id: str) -> Dict[str, Any]:
    service = await _get_google_service(user_id)
    if not service:
        return {"synced": 0, "skipped": True}

    time_min = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    page_token = None
    items: List[Dict[str, Any]] = []

    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                singleEvents=True,
                showDeleted=True,
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    synced = 0
    for event in items:
        google_event_id = event.get("id")
        if not google_event_id:
            continue

        if event.get("status") == "cancelled":
            await db.calendar_events.delete_one({"google_event_id": google_event_id, "user_id": user_id})
            continue

        start = event.get("start", {})
        end = event.get("end", {})
        start_value = start.get("dateTime") or start.get("date") or ""
        end_value = end.get("dateTime") or end.get("date") or ""
        existing = await db.calendar_events.find_one(
            {"google_event_id": google_event_id, "user_id": user_id}, {"_id": 0}
        )
        local_id = existing.get("id") if existing else str(uuid.uuid4().hex[:12])

        event_doc = {
            "id": local_id,
            "user_id": user_id,
            "google_event_id": google_event_id,
            "calendar_id": calendar_id,
            "title": event.get("summary", ""),
            "start": start_value,
            "end": end_value,
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "reminders": event.get("reminders"),
            "notes": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_at": existing.get("created_at") if existing else datetime.now(timezone.utc).isoformat(),
            "source": "google",
        }
        await db.calendar_events.update_one(
            {"google_event_id": google_event_id, "user_id": user_id},
            {"$set": event_doc},
            upsert=True,
        )
        synced += 1

    return {"synced": synced, "skipped": False}


async def _push_local_events_to_google(user_id: str, calendar_id: str) -> Dict[str, Any]:
    service = await _get_google_service(user_id)
    if not service:
        return {"pushed": 0, "skipped": True}

    local_events = await db.calendar_events.find(
        {
            "user_id": user_id,
            "$or": [
                {"google_event_id": {"$exists": False}},
                {"google_event_id": None},
                {"google_event_id": ""},
            ],
        },
        {"_id": 0},
    ).sort("start", 1).limit(300).to_list(300)

    pushed = 0
    for event in local_events:
        event_id = event.get("id")
        if not event_id:
            continue

        try:
            reminders = _build_reminders(event.get("reminders"), event.get("reminder_minutes"))
            event_body = {
                "summary": event.get("title") or "Untitled",
                "start": _format_event_time(event.get("start", "")),
                "end": _format_event_time(event.get("end", "")),
                "location": event.get("location", ""),
                "description": _combine_description(event.get("description", ""), event.get("notes", "")),
            }
            if reminders:
                event_body["reminders"] = reminders

            google_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            google_event_id = google_event.get("id")
            if not google_event_id:
                continue

            await db.calendar_events.update_one(
                {"id": event_id, "user_id": user_id},
                {
                    "$set": {
                        "google_event_id": google_event_id,
                        "calendar_id": calendar_id,
                        "source": "google",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            pushed += 1
        except Exception as e:
            logger.error(f"Failed to push local event {event_id} to Google for user {user_id}: {e}")

    return {"pushed": pushed, "skipped": False}


class CalendarEventCreate(BaseModel):
    user_id: str
    title: str
    start: str
    end: str
    description: str = ""
    location: str = ""
    notes: str = ""
    category: str = "meeting"
    color: str = ""
    recurrence: str = "none"  # none, daily, weekly, monthly
    recurrence_end: Optional[str] = None  # ISO date string or null for indefinite
    series_id: Optional[str] = None
    reminders: Optional[Dict[str, Any]] = None
    reminder_minutes: Optional[int] = None


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    recurrence: Optional[str] = None
    recurrence_end: Optional[str] = None
    reminders: Optional[Dict[str, Any]] = None
    reminder_minutes: Optional[int] = None


class AISuggestRequest(BaseModel):
    user_id: str
    title: str = ""
    category: str = "meeting"
    duration_minutes: int = 60
    preferred_date: Optional[str] = None  # YYYY-MM-DD


class BestSlotRequest(BaseModel):
    user_id: str
    title: str = ""
    category: str = "meeting"
    duration_minutes: int = 60


class BestSlotTelemetryRequest(BaseModel):
    user_id: str
    action: str
    recommendation: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class BestSlotCommitRequest(BaseModel):
    user_id: str
    recommendation: Dict[str, Any]


class CalendarSelectRequest(BaseModel):
    calendar_id: str


@router.get("/integrations/calendar/auth")
@router.get("/calendar/connect")
async def calendar_connect(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_google_calendar_configured():
        raise HTTPException(status_code=500, detail="Google Calendar not configured")

    state = await _create_calendar_oauth_state(user.user_id)
    return {"authorization_url": _build_google_auth_url(state, request)}


@router.get("/oauth/calendar/callback")
async def calendar_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle Google OAuth callback. Redirects to calendar page with status."""
    if error:
        logger.error(f"Google OAuth error: {error}")
        return RedirectResponse(url=f"/calendar?error={error}")

    if not is_google_calendar_configured():
        return RedirectResponse(url="/calendar?error=not_configured")

    if not code or not state:
        return RedirectResponse(url="/calendar?error=missing_params")

    state_doc = await db.calendar_oauth_states.find_one({"state": state}, {"_id": 0})
    if not state_doc:
        return RedirectResponse(url="/calendar?error=invalid_state")
    if _is_calendar_state_expired(state_doc):
        await db.calendar_oauth_states.delete_one({"state": state})
        return RedirectResponse(url="/calendar?error=invalid_state")

    await db.calendar_oauth_states.delete_one({"state": state})

    redirect_uri = _get_google_redirect_uri(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

        token_resp = token_response.json() if token_response.text else {}
        if token_response.status_code != 200 or token_resp.get("error") or not token_resp.get("access_token"):
            logger.error(f"Google token exchange error: {token_resp}")
            return RedirectResponse(url="/calendar?error=token_exchange_failed")

        existing_user = await db.users.find_one(
            {"user_id": state_doc["user_id"]}, {"_id": 0, "google_calendar.refresh_token": 1}
        )
        existing_refresh_token = (existing_user or {}).get("google_calendar", {}).get("refresh_token")
        resolved_refresh_token = token_resp.get("refresh_token") or existing_refresh_token

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_resp.get("expires_in", 3600)))
        await db.users.update_one(
            {"user_id": state_doc["user_id"]},
            {
                "$set": {
                    "google_calendar": {
                        "access_token": token_resp.get("access_token"),
                        "refresh_token": resolved_refresh_token,
                        "scope": token_resp.get("scope"),
                        "token_type": token_resp.get("token_type"),
                        "expires_at": expires_at.isoformat(),
                        "calendar_id": "primary",
                        "connected_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

        # Trigger initial two-way sync
        try:
            push_result = await _push_local_events_to_google(state_doc["user_id"], "primary")
            pull_result = await _sync_google_events(state_doc["user_id"], "primary")
            logger.info(
                f"Initial two-way sync complete for user {state_doc['user_id']} - "
                f"pushed={push_result.get('pushed', 0)} pulled={pull_result.get('synced', 0)}"
            )
        except Exception as e:
            logger.error(f"Initial calendar two-way sync failed: {e}")

        return RedirectResponse(url="/calendar?connected=1")
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(url="/calendar?error=connection_failed")


@router.get("/calendar/calendars")
async def get_google_calendars(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    service = await _get_google_service(user.user_id)
    if not service:
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    calendars = service.calendarList().list().execute().get("items", [])
    return {
        "calendars": [
            {
                "id": c.get("id"),
                "summary": c.get("summary"),
                "primary": c.get("primary", False),
                "timeZone": c.get("timeZone"),
            }
            for c in calendars
        ]
    }


@router.post("/calendar/select")
async def select_google_calendar(request: CalendarSelectRequest, req: Request):
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "google_calendar.calendar_id": request.calendar_id,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return {"success": True, "calendar_id": request.calendar_id}


@router.post("/calendar/disconnect")
async def disconnect_google_calendar(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$unset": {"google_calendar": ""}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    return {"success": True}


@router.post("/calendar/sync")
async def sync_calendar(request: Request):
    user = await _require_calendar_user(request)
    calendar_id = await _get_selected_calendar_id(user.user_id)
    push_result = await _push_local_events_to_google(user.user_id, calendar_id)
    pull_result = await _sync_google_events(user.user_id, calendar_id)
    return {
        "success": True,
        "sync_mode": "two_way",
        "pushed_local_events": push_result.get("pushed", 0),
        **pull_result,
    }


@router.get("/calendar/events/{user_id}")
async def get_calendar_events(user_id: str, request: Request):
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    google_connected = False
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    google_connected = bool(user_doc and user_doc.get("google_calendar", {}).get("access_token"))
    if google_connected:
        calendar_id = await _get_selected_calendar_id(user.user_id)
        await _sync_google_events(user.user_id, calendar_id)

    events = await db.calendar_events.find({"user_id": user_id}, {"_id": 0}).sort("start", 1).limit(200).to_list(200)
    source = "google_calendar" if google_connected else "local"
    return {"events": events, "source": source}


@router.post("/calendar/events")
async def create_calendar_event(request: CalendarEventCreate, req: Request):
    user = await _require_calendar_user(req)
    _assert_user_scope(user.user_id, request.user_id)
    recurrence = _normalize_recurrence(request.recurrence)
    _validate_event_window(request.start, request.end)

    google_event_id = None
    calendar_id = None

    calendar_id = await _get_selected_calendar_id(user.user_id)
    service = await _get_google_service(user.user_id)
    if service:
        reminders = _build_reminders(request.reminders, request.reminder_minutes)
        event_body = {
            "summary": request.title,
            "start": _format_event_time(request.start),
            "end": _format_event_time(request.end),
            "location": request.location,
            "description": _combine_description(request.description, request.notes),
        }
        if reminders:
            event_body["reminders"] = reminders
        google_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        google_event_id = google_event.get("id")

    event = {
        "id": str(uuid.uuid4().hex[:12]),
        "user_id": request.user_id,
        "google_event_id": google_event_id,
        "calendar_id": calendar_id,
        "title": request.title,
        "start": request.start,
        "end": request.end,
        "description": request.description,
        "location": request.location,
        "reminders": _build_reminders(request.reminders, request.reminder_minutes),
        "reminder_minutes": request.reminder_minutes,
        "reminder_sent": False,
        "notes": request.notes,
        "category": request.category,
        "color": request.color,
        "recurrence": recurrence,
        "recurrence_end": request.recurrence_end,
        "series_id": request.series_id or (str(uuid.uuid4().hex[:12]) if recurrence != "none" else None),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "google" if google_event_id else "local",
    }
    await db.calendar_events.insert_one({**event})

    # Generate recurring instances if recurrence is set
    recurring_events = []
    if recurrence != "none":
        recurring_events = await _generate_recurring_events(event, max_instances=60)

    # Send confirmation email + in-app notification
    try:
        from utils.notification_helper import create_notification_for_email

        if user:
            user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "email": 1, "name": 1})
            if user_doc:
                ev_start = request.start
                try:
                    dt = datetime.fromisoformat(ev_start.replace("Z", "+00:00"))
                    date_str = dt.strftime("%B %d, %Y at %I:%M %p")
                except Exception:
                    date_str = ev_start[:16] if ev_start else "TBD"
                cat = (request.category or "meeting").capitalize()
                loc = request.location or ""
                loc_str = f" at {loc}" if loc else ""
                msg = f'Your {cat} "{request.title}" has been scheduled for {date_str}{loc_str}.'
                await create_notification_for_email(
                    user.user_id, user_doc["email"], f"Confirmed: {request.title}", msg, "new_booking"
                )
    except Exception as e:
        logger.error(f"Event create notification error: {e}")

    return {"success": True, "event": event, "recurring_count": len(recurring_events)}


@router.put("/calendar/events/{event_id}")
async def update_calendar_event(event_id: str, request: CalendarEventUpdate, req: Request):
    user = await _require_calendar_user(req)
    event_doc = await db.calendar_events.find_one({"id": event_id}, {"_id": 0})
    if not event_doc:
        raise HTTPException(status_code=404, detail="Event not found")
    _assert_user_scope(user.user_id, event_doc.get("user_id", ""))

    updates: Dict[str, Any] = {k: v for k, v in request.dict().items() if v is not None}
    if "recurrence" in updates:
        updates["recurrence"] = _normalize_recurrence(updates.get("recurrence"))
    next_start = updates.get("start", event_doc.get("start"))
    next_end = updates.get("end", event_doc.get("end"))
    if next_start and next_end:
        _validate_event_window(str(next_start), str(next_end))

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.calendar_events.update_one({"id": event_id}, {"$set": updates})

    if event_doc.get("google_event_id"):
        calendar_id = await _get_selected_calendar_id(user.user_id)
        service = await _get_google_service(user.user_id)
        if service:
            reminders = _build_reminders(updates.get("reminders"), updates.get("reminder_minutes"))
            event_body = {
                "summary": updates.get("title", event_doc.get("title")),
                "start": _format_event_time(updates.get("start", event_doc.get("start"))),
                "end": _format_event_time(updates.get("end", event_doc.get("end"))),
                "location": updates.get("location", event_doc.get("location")),
                "description": _combine_description(
                    updates.get("description", event_doc.get("description", "")),
                    updates.get("notes", event_doc.get("notes", "")),
                ),
            }
            if reminders:
                event_body["reminders"] = reminders
            service.events().update(
                calendarId=calendar_id,
                eventId=event_doc.get("google_event_id"),
                body=event_body,
            ).execute()

    updated = await db.calendar_events.find_one({"id": event_id}, {"_id": 0})

    # Send update/reschedule email + in-app notification
    try:
        from utils.notification_helper import create_notification_for_email

        if user:
            user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "email": 1, "name": 1})
            if user_doc and updated:
                ev_title = updated.get("title", "Untitled Event")
                ev_start = updated.get("start", "")
                try:
                    dt = datetime.fromisoformat(ev_start.replace("Z", "+00:00"))
                    date_str = dt.strftime("%B %d, %Y at %I:%M %p")
                except Exception:
                    date_str = ev_start[:16] if ev_start else "TBD"
                changed = []
                if "start" in updates or "end" in updates:
                    changed.append("rescheduled")
                if "title" in updates:
                    changed.append("renamed")
                if "location" in updates:
                    changed.append("location updated")
                change_str = " & ".join(changed) if changed else "updated"
                msg = f'Your event "{ev_title}" has been {change_str}. New time: {date_str}.'
                await create_notification_for_email(
                    user.user_id, user_doc["email"], f"Updated: {ev_title}", msg, "booking_rescheduled"
                )
    except Exception as e:
        logger.error(f"Event update notification error: {e}")

    return {"success": True, "event": updated}


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: str, req: Request):
    user = await _require_calendar_user(req)
    event_doc = await db.calendar_events.find_one({"id": event_id}, {"_id": 0})
    if not event_doc:
        raise HTTPException(status_code=404, detail="Event not found")
    _assert_user_scope(user.user_id, event_doc.get("user_id", ""))

    if event_doc.get("google_event_id"):
        calendar_id = await _get_selected_calendar_id(user.user_id)
        service = await _get_google_service(user.user_id)
        if service:
            service.events().delete(calendarId=calendar_id, eventId=event_doc.get("google_event_id")).execute()

    result = await db.calendar_events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")

    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

    # Send cancellation email
    try:
        user_doc = await db.users.find_one({"user_id": event_doc.get("user_id")}, {"_id": 0, "email": 1, "name": 1})
        if user_doc and user_doc.get("email"):
            from utils.email_service import is_email_configured

            if is_email_configured():
                title = event_doc.get("title", "Untitled Event")
                event_doc.get("category", "meeting").capitalize()
                try:
                    ev_start = datetime.fromisoformat(event_doc["start"].replace("Z", "+00:00"))
                    date_str = ev_start.strftime("%B %d, %Y")
                    time_str = ev_start.strftime("%I:%M %p")
                except Exception:
                    date_str = event_doc.get("start", "")[:10]
                    time_str = ""
                from utils.email_service import send_catalog_template
                recipient_email = str(user_doc.get("email") or "").strip()
                recipient_norm = recipient_email.lower()
                dedupe_key = f"calendar_event_cancelled:{event_id}:{recipient_norm}"
                reserved = await reserve_dispatch_once(
                    dedupe_key=dedupe_key,
                    event_type="calendar_event_cancelled",
                    channel="email",
                    recipient=recipient_norm,
                    payload={"event_id": event_id, "event_title": title, "event_date": date_str},
                )
                if reserved:
                    result = await send_catalog_template(
                        recipient_email,
                        "calendar_event_cancelled",
                        user_name=user_doc.get("name", ""),
                        event_title=title,
                        event_date=date_str,
                        dedupe_key=dedupe_key,
                    )
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="sent" if bool(result.get("success")) else "failed",
                        extra={"sent_at": datetime.now(timezone.utc).isoformat()} if bool(result.get("success")) else {"error": str(result.get("error") or "send_failed")[:300]},
                    )
            # Also create in-app notification
            from utils.notification_helper import create_notification

            await create_notification(
                event_doc.get("user_id"),
                f"Cancelled: {title}",
                f'Your event "{title}" on {date_str} at {time_str} has been cancelled and removed from your agenda.',
                "booking_cancelled",
            )
    except Exception as e:
        logger.error(f"Cancel email error: {e}")

    return {"success": True, "message": "Event deleted"}


@router.delete("/calendar/series/{series_id}")
async def delete_event_series(series_id: str, req: Request):
    """Delete all events in a recurring series."""
    user = await _require_calendar_user(req)
    result = await db.calendar_events.delete_many({"series_id": series_id, "user_id": user.user_id})
    return {"success": True, "deleted_count": result.deleted_count}


async def _generate_recurring_events(base_event: dict, max_instances: int = 60):
    """Generate future instances of a recurring event."""
    recurrence = base_event.get("recurrence", "none")
    if recurrence == "none":
        return []

    try:
        start_dt = datetime.fromisoformat(base_event["start"].replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(base_event["end"].replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return []

    duration = end_dt - start_dt
    recurrence_end = None
    if base_event.get("recurrence_end"):
        try:
            recurrence_end = datetime.fromisoformat(base_event["recurrence_end"].replace("Z", "+00:00"))
        except ValueError:
            pass

    events = []
    current_start = start_dt
    for i in range(1, max_instances + 1):
        if recurrence == "daily":
            current_start = start_dt + timedelta(days=i)
        elif recurrence == "weekly":
            current_start = start_dt + timedelta(weeks=i)
        elif recurrence == "monthly":
            current_start = _add_months_preserving_day(start_dt, i)
        else:
            break

        if recurrence_end and current_start > recurrence_end:
            break

        current_end = current_start + duration
        ev = {
            "id": str(uuid.uuid4().hex[:12]),
            "user_id": base_event["user_id"],
            "google_event_id": None,
            "calendar_id": base_event.get("calendar_id"),
            "title": base_event["title"],
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
            "description": base_event.get("description", ""),
            "location": base_event.get("location", ""),
            "reminders": base_event.get("reminders"),
            "notes": base_event.get("notes", ""),
            "category": base_event.get("category", "meeting"),
            "color": base_event.get("color", ""),
            "recurrence": recurrence,
            "recurrence_end": base_event.get("recurrence_end"),
            "series_id": base_event.get("series_id"),
            "reminder_minutes": base_event.get("reminder_minutes"),
            "reminder_sent": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "local",
        }
        events.append(ev)

    if events:
        await db.calendar_events.insert_many([{**e} for e in events])
    return events


@router.post("/calendar/ai-suggest")
async def ai_suggest_time_slots(request: AISuggestRequest, req: Request):
    """Use GPT-4o to suggest optimal time slots based on existing schedule."""
    user = await _require_calendar_user(req)
    _assert_user_scope(user.user_id, request.user_id)

    # Get existing events for the user (next 7 days)
    preferred = request.preferred_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events = (
        await db.calendar_events.find(
            {"user_id": request.user_id}, {"_id": 0, "title": 1, "start": 1, "end": 1, "category": 1}
        )
        .sort("start", 1)
        .limit(100)
        .to_list(100)
    )

    # Build schedule summary for AI
    schedule_lines = []
    for ev in events:
        try:
            s = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(ev["end"].replace("Z", "+00:00"))
            schedule_lines.append(
                f"- {ev.get('title', 'Untitled')}: {s.strftime('%Y-%m-%d %H:%M')} to {e.strftime('%H:%M')} [{ev.get('category', 'general')}]"
            )
        except Exception:
            pass

    schedule_text = "\n".join(schedule_lines[-30:]) if schedule_lines else "No existing events."

    prompt = f"""You are a smart scheduling assistant. Analyze the user's existing schedule and suggest 5 optimal time slots for a new event.

Event to schedule: "{request.title or "New event"}"
Category: {request.category}
Duration: {request.duration_minutes} minutes
Preferred date: {preferred}

User's existing schedule:
{schedule_text}

Rules:
1. Avoid conflicts with existing events
2. Prefer productive hours (8 AM - 6 PM) for work/meetings
3. Suggest morning slots for health/fitness
4. Suggest evening/weekend slots for personal/social
5. Space events with 15-30 min buffers
6. Consider the event category when suggesting times

Return EXACTLY 5 suggestions as a JSON array. Each object must have:
- "start": ISO datetime string (YYYY-MM-DDTHH:MM:00)
- "end": ISO datetime string (YYYY-MM-DDTHH:MM:00)
- "reason": brief explanation (max 40 chars)
- "score": confidence 1-100

Return ONLY the JSON array, no markdown or extra text."""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ai-suggest-{request.user_id}-{uuid.uuid4().hex[:6]}",
            system_message="You are a smart scheduling assistant. Return ONLY valid JSON arrays.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))
        raw = response.text if hasattr(response, "text") else str(response)
        raw = raw.strip()
        # Parse JSON from response
        import json

        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        suggestions = json.loads(raw)
        return {"success": True, "suggestions": suggestions[:5]}
    except Exception as e:
        logger.error(f"AI suggest error: {e}")
        # Fallback: generate simple time slots
        fallback = []
        base = datetime.fromisoformat(f"{preferred}T09:00:00")
        for i, hour in enumerate([9, 11, 14, 16, 18]):
            s = base.replace(hour=hour)
            e = s + timedelta(minutes=request.duration_minutes)
            fallback.append(
                {
                    "start": s.isoformat(),
                    "end": e.isoformat(),
                    "reason": f"Available {hour}:00 slot",
                    "score": 80 - i * 5,
                }
            )
        return {"success": True, "suggestions": fallback}


@router.post("/calendar/recommend-best-slot")
async def recommend_best_slot(request: BestSlotRequest, req: Request):
    """Deterministic one-click best-slot recommendation for Feature 34 control ops."""
    user = await _require_calendar_user(req)
    _assert_user_scope(user.user_id, request.user_id)

    duration = max(15, min(int(request.duration_minutes or 60), 180))
    category = str(request.category or "meeting").strip().lower() or "meeting"

    result = await _recommend_best_slot_for_user(user.user_id, duration, category)
    return {
        "success": True,
        "recommendation": result.get("recommendation", {}),
        "alternatives": result.get("alternatives", []),
        "meta": result.get("meta", {}),
    }


@router.post("/calendar/recommend-best-slot/telemetry")
async def best_slot_telemetry(request: BestSlotTelemetryRequest, req: Request):
    user = await _require_calendar_user(req)
    _assert_user_scope(user.user_id, request.user_id)

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    plan_scope = compute_effective_plan(user_doc or {})
    telemetry = await _record_best_slot_telemetry(
        user_id=user.user_id,
        action=request.action,
        plan_scope=plan_scope,
        recommendation=request.recommendation,
        metadata=request.metadata,
    )
    return {"success": True, "telemetry_id": telemetry.get("id"), "action": telemetry.get("action")}


@router.get("/calendar/recommend-best-slot/reward-badge/{user_id}")
async def best_slot_weekly_reward_badge(user_id: str, req: Request):
    """Return weekly best-slot reward badge progress for repeat engagement tuning."""
    user = await _require_calendar_user(req)
    _assert_user_scope(user.user_id, user_id)

    now = datetime.now(timezone.utc)
    window_start_iso = (now - timedelta(days=7)).isoformat()

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    plan_scope = compute_effective_plan(user_doc or {})

    rows = await db.calendar_best_slot_telemetry.find(
        {
            "user_id": user.user_id,
            "action": "accepted",
            "created_at": {"$gte": window_start_iso},
        },
        {"_id": 0, "metadata": 1},
    ).to_list(500)

    accepted_this_week = len(rows)
    accepted_commit = 0
    accepted_prefill = 0
    accepted_legacy = 0
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        mode = str(metadata.get("mode") or "").strip().lower()
        if mode == "commit":
            accepted_commit += 1
        elif mode == "prefill-form":
            accepted_prefill += 1
        else:
            accepted_legacy += 1

    badge = _build_weekly_best_slot_reward_badge(
        plan_scope=plan_scope,
        accepted_this_week=accepted_this_week,
        accepted_commit=accepted_commit,
        accepted_prefill=accepted_prefill,
        accepted_legacy=accepted_legacy,
        now=now,
    )

    return {
        "success": True,
        "feature": "book-meeting",
        "protocol": "platform_locked",
        "user_id": user.user_id,
        "badge": badge,
    }


@router.post("/calendar/recommend-best-slot/commit")
async def commit_best_slot(request: BestSlotCommitRequest, req: Request):
    """One-click confirmation path: commit recommended slot directly to calendar events."""
    user = await _require_calendar_user(req)
    _assert_user_scope(user.user_id, request.user_id)

    recommendation = request.recommendation or {}
    start = str(recommendation.get("start") or "").strip()
    end = str(recommendation.get("end") or "").strip()
    if not start or not end:
        raise HTTPException(status_code=400, detail="Recommendation must include start and end")

    _validate_event_window(start, end)
    start_dt = _parse_calendar_dt(start)
    end_dt = _parse_calendar_dt(end)

    existing_conflict = await db.calendar_events.find_one(
        {
            "user_id": user.user_id,
            "start": {"$lt": end_dt.isoformat()},
            "end": {"$gt": start_dt.isoformat()},
        },
        {"_id": 0, "id": 1},
    )
    if existing_conflict:
        raise HTTPException(status_code=409, detail="Recommended slot now conflicts with an existing event")
    category = str(recommendation.get("category") or "meeting").strip().lower() or "meeting"
    title = str(recommendation.get("title") or "Meeting Session").strip()[:160] or "Meeting Session"
    reason = str(recommendation.get("reason") or "Committed from best-slot recommendation").strip()[:600]

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    plan_scope = compute_effective_plan(user_doc or {})

    event_id = str(uuid.uuid4().hex[:12])
    calendar_id = await _get_selected_calendar_id(user.user_id)
    google_event_id = None
    source = "local"

    service = await _get_google_service(user.user_id)
    if service:
        try:
            event_body = {
                "summary": title,
                "start": _format_event_time(start),
                "end": _format_event_time(end),
                "description": reason,
            }
            google_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            google_event_id = google_event.get("id")
            source = "google"
        except Exception as exc:
            logger.error(f"Best-slot commit Google sync failed for user {user.user_id}: {exc}")

    event_doc = {
        "id": event_id,
        "user_id": user.user_id,
        "google_event_id": google_event_id,
        "calendar_id": calendar_id,
        "title": title,
        "start": start,
        "end": end,
        "description": reason,
        "location": "",
        "notes": "Committed via one-click best-slot suggestion",
        "category": category,
        "color": "",
        "recurrence": "none",
        "recurrence_end": None,
        "series_id": None,
        "reminder_minutes": 15,
        "reminder_sent": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    await db.calendar_events.insert_one({**event_doc})

    telemetry = await _record_best_slot_telemetry(
        user_id=user.user_id,
        action="accepted",
        plan_scope=plan_scope,
        recommendation=recommendation,
        metadata={"mode": "commit", "event_id": event_id},
    )

    return {
        "success": True,
        "event": event_doc,
        "telemetry_id": telemetry.get("id"),
        "message": "Recommendation committed to your calendar",
    }


@router.put("/calendar/events/{event_id}/reschedule")
async def reschedule_event(event_id: str, req: Request):
    """Quick reschedule - move an event to a new date (drag-and-drop)."""
    user = await _require_calendar_user(req)
    body = await req.json()
    new_date = body.get("new_date")  # YYYY-MM-DD
    if not new_date:
        raise HTTPException(status_code=400, detail="new_date is required")

    event_doc = await db.calendar_events.find_one({"id": event_id}, {"_id": 0})
    if not event_doc:
        raise HTTPException(status_code=404, detail="Event not found")
    _assert_user_scope(user.user_id, event_doc.get("user_id", ""))

    try:
        old_start = datetime.fromisoformat(event_doc["start"].replace("Z", "+00:00"))
        old_end = datetime.fromisoformat(event_doc["end"].replace("Z", "+00:00"))
        duration = old_end - old_start
        parts = new_date.split("-")
        new_start = old_start.replace(year=int(parts[0]), month=int(parts[1]), day=int(parts[2]))
        new_end = new_start + duration
        await db.calendar_events.update_one(
            {"id": event_id},
            {
                "$set": {
                    "start": new_start.isoformat(),
                    "end": new_end.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "reminder_sent": False,
                }
            },
        )

        from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

        # Send rescheduling email
        try:
            user_doc = await db.users.find_one({"user_id": event_doc.get("user_id")}, {"_id": 0, "email": 1, "name": 1})
            if user_doc and user_doc.get("email"):
                from utils.email_service import is_email_configured

                if is_email_configured():
                    title = event_doc.get("title", "Untitled Event")
                    datetime.fromisoformat(event_doc["start"].replace("Z", "+00:00")).strftime("%B %d, %Y")
                    new_date_fmt = new_start.strftime("%B %d, %Y")
                    new_start.strftime("%I:%M %p")
                    from utils.email_service import send_catalog_template
                    recipient_email = str(user_doc.get("email") or "").strip()
                    recipient_norm = recipient_email.lower()
                    dedupe_key = f"calendar_event_rescheduled:{event_id}:{new_date}:{recipient_norm}"
                    reserved = await reserve_dispatch_once(
                        dedupe_key=dedupe_key,
                        event_type="calendar_event_rescheduled",
                        channel="email",
                        recipient=recipient_norm,
                        payload={"event_id": event_id, "event_title": title, "new_date": new_date_fmt},
                    )
                    if reserved:
                        result = await send_catalog_template(
                            recipient_email,
                            "calendar_event_rescheduled",
                            user_name=user_doc.get("name", ""),
                            event_title=title,
                            new_date=new_date_fmt,
                            dedupe_key=dedupe_key,
                        )
                        await mark_dispatch_status(
                            dedupe_key=dedupe_key,
                            status="sent" if bool(result.get("success")) else "failed",
                            extra={"sent_at": datetime.now(timezone.utc).isoformat()} if bool(result.get("success")) else {"error": str(result.get("error") or "send_failed")[:300]},
                        )
        except Exception as e:
            logger.error(f"Reschedule email error: {e}")

        return {"success": True, "new_start": new_start.isoformat(), "new_end": new_end.isoformat()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def send_agenda_event_reminders():
    """Background job: send multi-interval reminders (5, 10, 15, 30, 45 min) for agenda events."""
    from utils.notification_helper import create_notification_for_email

    REMINDER_INTERVALS = [5, 10, 15, 30, 45]
    now = datetime.now(timezone.utc)

    # Find upcoming events (within next 50 minutes to cover all intervals)
    window_end = (now + timedelta(minutes=50)).isoformat()
    events_cursor = db.calendar_events.find({"start": {"$gte": now.isoformat(), "$lte": window_end}}, {"_id": 0}).limit(
        500
    )
    events = await events_cursor.to_list(500)

    sent_count = 0
    for ev in events:
        try:
            event_start = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            if event_start.tzinfo is None:
                event_start = event_start.replace(tzinfo=timezone.utc)

            if event_start <= now:
                continue

            user_id = ev.get("user_id", "")
            if not user_id:
                continue

            minutes_until = (event_start - now).total_seconds() / 60

            for interval in REMINDER_INTERVALS:
                sent_key = f"reminder_{interval}_sent"
                # Check: within 2-min window of the interval and not already sent
                if abs(minutes_until - interval) > 2:
                    continue
                if ev.get(sent_key):
                    continue

                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                if not user_doc:
                    break

                title = ev.get("title", "Upcoming Event")
                cat = ev.get("category", "meeting").capitalize()
                start_str = event_start.strftime("%I:%M %p")
                event_date = event_start.strftime("%b %d, %Y")
                location = ev.get("location", "")
                loc_str = f" at {location}" if location else ""

                notif_title = f"Reminder: {title} in {interval} min"
                notif_msg = f'Your {cat} "{title}" starts at {start_str} on {event_date}{loc_str}. Get ready!'

                await create_notification_for_email(
                    user_id, user_doc.get("email", ""), notif_title, notif_msg, "agenda_reminder"
                )

                # Mark this interval as sent
                await db.calendar_events.update_one({"id": ev["id"]}, {"$set": {sent_key: True}})
                sent_count += 1
                logger.info(f"Sent {interval}min reminder for event '{title}' (user={user_id})")

        except Exception as e:
            logger.error(f"Agenda reminder error for event {ev.get('id')}: {e}")

    if sent_count > 0:
        logger.info(f"Sent {sent_count} agenda event reminders")


@router.get("/calendar/status")
async def calendar_status(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_doc = await _enforce_calendar_min_plan(user.user_id)
    gc = (user_doc or {}).get("google_calendar", {})
    google_connected = bool(user_doc and gc.get("access_token"))
    selected_calendar_id = gc.get("calendar_id")
    connection_lost = bool(gc.get("disconnect_alert_sent_at")) and not google_connected
    user_timezone = (user_doc or {}).get("timezone", "UTC")

    return {
        "google_available": is_google_calendar_configured(),
        "google_connected": google_connected,
        "connection_lost": connection_lost,
        "provider": "google" if is_google_calendar_configured() else "local",
        "auth_endpoint": "/api/integrations/calendar/auth" if is_google_calendar_configured() else None,
        "sync_mode": "two_way" if google_connected else "local_only",
        "selected_calendar_id": selected_calendar_id,
        "timezone": user_timezone,
    }


@router.put("/calendar/timezone")
async def set_calendar_timezone(request: Request):
    """Save user's detected timezone."""
    user = await _require_calendar_user(request)
    body = await request.json()
    tz = body.get("timezone", "UTC")
    await db.users.update_one(
        {"user_id": user.user_id}, {"$set": {"timezone": tz, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "timezone": tz}


@router.get("/calendar/reminders/{user_id}")
async def get_due_reminders(user_id: str, request: Request):
    """Get events with reminders due in the next 60 minutes."""
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    now = datetime.now(timezone.utc)
    window = now + timedelta(minutes=60)
    events = (
        await db.calendar_events.find(
            {"user_id": user_id, "start": {"$gte": now.isoformat(), "$lte": window.isoformat()}}, {"_id": 0}
        )
        .sort("start", 1)
        .to_list(20)
    )
    return {"reminders": events}


@router.get("/calendar/upcoming/{user_id}")
async def get_upcoming_events(user_id: str, request: Request, limit: int = 5):
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    calendar_id = await _get_selected_calendar_id(user.user_id)
    await _sync_google_events(user.user_id, calendar_id)

    now = datetime.now(timezone.utc).isoformat()
    events = (
        await db.calendar_events.find({"user_id": user_id, "start": {"$gte": now}}, {"_id": 0})
        .sort("start", 1)
        .limit(limit)
        .to_list(limit)
    )
    return {"events": events}


# ── AI Smart Scheduling ──


@router.get("/calendar/smart-suggestions/{user_id}")
async def smart_suggestions(user_id: str, request: Request):
    """AI analyzes calendar patterns and suggests optimal slots + focus time."""
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)

    now = datetime.now(timezone.utc)
    past_start = (now - timedelta(days=14)).isoformat()
    future_end = (now + timedelta(days=7)).isoformat()

    past_events = (
        await db.calendar_events.find(
            {"user_id": user_id, "start": {"$gte": past_start, "$lt": now.isoformat()}},
            {"_id": 0, "title": 1, "start": 1, "end": 1, "location": 1},
        )
        .sort("start", 1)
        .to_list(100)
    )

    upcoming_events = (
        await db.calendar_events.find(
            {"user_id": user_id, "start": {"$gte": now.isoformat(), "$lte": future_end}},
            {"_id": 0, "title": 1, "start": 1, "end": 1, "location": 1},
        )
        .sort("start", 1)
        .to_list(100)
    )

    user_tz = "UTC"
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "timezone": 1})
    if user_doc:
        user_tz = user_doc.get("timezone", "UTC")

    past_summary = (
        "\n".join(
            [f"- {e.get('title', '?')} at {e.get('start', '?')} to {e.get('end', '?')}" for e in past_events[:30]]
        )
        or "No recent events"
    )
    upcoming_summary = (
        "\n".join(
            [f"- {e.get('title', '?')} at {e.get('start', '?')} to {e.get('end', '?')}" for e in upcoming_events[:20]]
        )
        or "No upcoming events"
    )

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI not configured")

    prompt = f"""Analyze this user's calendar and return JSON with smart scheduling suggestions.

Current time: {now.isoformat()}
User timezone: {user_tz}
Today: {now.strftime("%A, %B %d, %Y")}

PAST 2 WEEKS EVENTS:
{past_summary}

UPCOMING 7 DAYS EVENTS:
{upcoming_summary}

Return ONLY valid JSON:
{{
  "patterns": [
    "short insight about their schedule pattern (max 3)"
  ],
  "suggested_slots": [
    {{
      "title": "suggested event name",
      "start": "ISO datetime",
      "end": "ISO datetime",
      "reason": "why this slot is good",
      "type": "meeting|focus|break|exercise"
    }}
  ],
  "focus_blocks": [
    {{
      "title": "Focus Time",
      "start": "ISO datetime",
      "end": "ISO datetime",
      "reason": "why this is a good focus block"
    }}
  ],
  "busy_score": 0-100,
  "recommendation": "one sentence overall scheduling advice"
}}

Rules:
- Suggest 3-5 optimal time slots in the next 7 days that DON'T conflict with existing events
- Suggest 2-3 focus time blocks (90-120 min) in low-activity periods
- Focus blocks should be on weekdays between 8am-6pm in user's timezone
- busy_score: 0=empty calendar, 100=completely packed
- Be specific with dates and times, use ISO format
- Analyze patterns like: morning vs afternoon preference, meeting density, break gaps
"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"smart-sched-{user_id}-{uuid.uuid4().hex[:6]}",
            system_message="You are a smart calendar scheduling assistant. Return only valid JSON.",
        ).with_model("openai", "gpt-4o-mini")
        response = await chat.send_message(UserMessage(text=prompt))
        text = response.strip()

        import json as json_mod

        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json_mod.loads(text)
        return {"success": True, "analysis": data}
    except Exception as e:
        logger.error(f"Smart scheduling AI error: {e}")
        raise HTTPException(status_code=500, detail="AI analysis failed")


@router.post("/calendar/auto-focus-blocks/{user_id}")
async def create_focus_blocks(user_id: str, request: Request):
    """Create AI-recommended focus time blocks on the user's calendar."""
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)

    body = await request.json()
    blocks = body.get("blocks", [])
    if not blocks:
        raise HTTPException(status_code=400, detail="No blocks provided")

    created = []
    calendar_id = await _get_selected_calendar_id(user_id)
    service = await _get_google_service(user_id)

    for block in blocks[:5]:
        google_event_id = None
        if service:
            try:
                event_body = {
                    "summary": block.get("title", "Focus Time"),
                    "start": _format_event_time(block["start"]),
                    "end": _format_event_time(block["end"]),
                    "description": block.get("reason", "AI-suggested focus time block"),
                    "colorId": "7",
                }
                google_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
                google_event_id = google_event.get("id")
            except Exception as e:
                logger.error(f"Failed to create Google event for focus block: {e}")

        event = {
            "id": str(uuid.uuid4().hex[:12]),
            "user_id": user_id,
            "google_event_id": google_event_id,
            "calendar_id": calendar_id,
            "title": block.get("title", "Focus Time"),
            "start": block["start"],
            "end": block["end"],
            "description": block.get("reason", "AI-suggested focus time block"),
            "location": "",
            "notes": "Auto-created by AI Smart Scheduling",
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 5}]},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "google" if google_event_id else "local",
            "ai_generated": True,
        }
        await db.calendar_events.insert_one({**event})
        created.append(event)

    return {"success": True, "created": created, "count": len(created)}


# ── AI Image Generation ──
STYLE_PRESETS = {
    "cinematic": "Cinematic lighting, dramatic depth of field, rich contrast, filmic color grading.",
    "studio": "Clean studio lighting, product-shot precision, neutral background, crisp edges.",
    "editorial": "Editorial photography, natural light, candid realism, balanced tones.",
    "illustration": "High-detail illustration, painterly textures, bold yet clean shapes.",
    "clarity": "Accessibility-focused clarity, high legibility, simplified forms, low visual noise.",
}

QUALITY_PRESETS = {
    "standard": "High resolution, sharp focus, accurate textures, minimal noise.",
    "ultra": "Ultra-high resolution, 8K detail, immaculate sharpness, pristine textures, noise-free.",
}


class ImageGenRequest(BaseModel):
    prompt: str
    user_id: str = "guest"
    size: str = "1024x1024"
    # "base64" (default) or "url" (recommended for web to avoid large JSON payloads)
    response_format: str = "base64"
    style: Optional[str] = None
    quality: Optional[str] = None


AI_IMAGE_DAILY_LIMITS = {
    "free": 3,
    "basic": 60,
    "premium": -1,
}


def _resolve_ai_image_plan(user_doc: dict | None) -> str:
    if not user_doc:
        return "free"
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in {"free", "basic", "premium"} else "free"


async def _enforce_ai_image_limit(user_id: str, plan: str) -> tuple[int, int]:
    limit = int(AI_IMAGE_DAILY_LIMITS.get(plan, AI_IMAGE_DAILY_LIMITS["free"]))
    if limit < 0:
        return 0, limit
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.ai_image_usage_log.count_documents(
        {"user_id": user_id, "created_at": {"$gte": start}}
    )
    if used >= limit:
        scope = "Limited access" if plan == "free" else "Almost unlimited access"
        raise HTTPException(status_code=429, detail=f"{scope}: daily image generation limit reached ({limit}).")
    return used, limit


async def _log_ai_image_usage(user_id: str, plan: str, prompt: str) -> None:
    await db.ai_image_usage_log.insert_one(
        {
            "user_id": user_id,
            "plan": plan,
            "prompt": prompt[:220],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def build_image_prompt(prompt: str, style: Optional[str], quality: Optional[str]) -> str:
    style_key = (style or "").lower().strip()
    quality_key = (quality or "").lower().strip()
    style_note = STYLE_PRESETS.get(style_key, "")
    quality_note = QUALITY_PRESETS.get(quality_key, "")
    parts = [
        "Stunning, award-winning composition, professional photography quality.",
    ]
    if quality_note:
        parts.append(quality_note)
    if style_note:
        parts.append(style_note)
    parts.append(f"Subject: {prompt}.")
    parts.append(
        "Avoid: blurry, low resolution, watermark, text artifacts, deformed anatomy, duplicated objects, oversaturation."
    )
    return " ".join(parts)


@router.post("/ai-image")
async def generate_image(request: ImageGenRequest):
    prompt = request.prompt
    user_doc = await db.users.find_one(
        {"user_id": request.user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    plan = _resolve_ai_image_plan(user_doc)
    used, limit = await _enforce_ai_image_limit(request.user_id, plan)

    enhanced_prompt = build_image_prompt(prompt, request.style, request.quality)
    api_key = os.environ.get("EMERGENT_LLM_KEY") or EMERGENT_LLM_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured")
    image_gen = OpenAIImageGeneration(api_key=api_key)

    import time as _time

    gen_start = _time.time()
    last_err = None
    retries = 0
    for attempt in range(3):
        try:
            images = await image_gen.generate_images(prompt=enhanced_prompt, model="gpt-image-1", number_of_images=1)
            if not images:
                raise HTTPException(status_code=500, detail="No image was generated")

            duration_ms = (_time.time() - gen_start) * 1000
            # Log success
            await db.image_gen_logs.insert_one(
                {
                    "status": "success",
                    "prompt": prompt[:200],
                    "retries": retries,
                    "duration_ms": round(duration_ms),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            if request.response_format == "url":
                image_id = uuid.uuid4().hex
                await db.ai_images.insert_one(
                    {
                        "id": image_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "content_type": "image/png",
                        "bytes_b64": base64.b64encode(images[0]).decode("utf-8"),
                    }
                )
                await _log_ai_image_usage(request.user_id, plan, prompt)
                return {
                    "image_url": f"/api/ai-image/file/{image_id}",
                    "prompt": prompt,
                    "plan_scope": plan,
                    "daily_limit": limit,
                    "used_today": used + 1,
                }

            image_base64 = base64.b64encode(images[0]).decode("utf-8")
            await _log_ai_image_usage(request.user_id, plan, prompt)
            return {
                "image_base64": image_base64,
                "prompt": prompt,
                "plan_scope": plan,
                "daily_limit": limit,
                "used_today": used + 1,
            }
        except HTTPException:
            raise
        except Exception as e:
            last_err = e
            retries = attempt + 1
            logger.warning(f"Image gen attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                import asyncio

                await asyncio.sleep(1 * (attempt + 1))

    duration_ms = (_time.time() - gen_start) * 1000
    # Log failure
    await db.image_gen_logs.insert_one(
        {
            "status": "failed",
            "prompt": prompt[:200],
            "retries": retries,
            "duration_ms": round(duration_ms),
            "error": str(last_err)[:300],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    logger.error(f"Image gen failed after 3 attempts: {last_err}")
    raise HTTPException(status_code=500, detail=f"Image generation failed: {last_err}")


@router.post("/ai-image/generate")
async def generate_image_alias(request: ImageGenRequest):
    return await generate_image(request)


@router.get("/ai-image/file/{image_id}")
async def get_generated_image_file(image_id: str):
    doc = await db.ai_images.find_one({"id": image_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")
    data = base64.b64decode(doc.get("bytes_b64") or "")
    return Response(content=data, media_type=doc.get("content_type") or "image/png")


# ── Calendar Sharing ──


@router.post("/calendar/share")
async def create_calendar_share(request: Request):
    """Generate a public share link for user's calendar availability."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    days = int(body.get("days", 7))
    show_titles = bool(body.get("show_titles", False))
    name = body.get("name", "My Availability")

    now = datetime.now(timezone.utc)
    token = uuid.uuid4().hex[:16]

    share_doc = {
        "token": token,
        "user_id": user.user_id,
        "name": name,
        "show_titles": show_titles,
        "days": days,
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(days=days)).isoformat(),
        "created_at": now.isoformat(),
        "active": True,
    }
    await db.calendar_shares.insert_one(share_doc)

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "name": 1})
    share_doc.pop("_id", None)
    share_doc["owner_name"] = (user_doc or {}).get("name", "User")

    return {"success": True, "share": share_doc}


@router.get("/calendar/shares/{user_id}")
async def list_calendar_shares(user_id: str, request: Request):
    """List all active share links for a user."""
    user = await get_current_user(request)
    if not user or user.user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    shares = (
        await db.calendar_shares.find({"user_id": user_id, "active": True}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(20)
    )
    return {"shares": shares}


@router.delete("/calendar/share/{token}")
async def revoke_calendar_share(token: str, request: Request):
    """Revoke a calendar share link."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.calendar_shares.update_one({"token": token, "user_id": user.user_id}, {"$set": {"active": False}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Share link not found")
    return {"success": True}


@router.get("/calendar/shared/{token}")
async def view_shared_calendar(token: str):
    """Public endpoint: view shared calendar availability. No auth required."""
    share = await db.calendar_shares.find_one({"token": token, "active": True}, {"_id": 0})
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or expired")

    user_doc = await db.users.find_one({"user_id": share["user_id"]}, {"_id": 0, "name": 1, "timezone": 1})
    owner_name = (user_doc or {}).get("name", "User")
    owner_tz = (user_doc or {}).get("timezone", "UTC")

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=share.get("days", 7))

    events = (
        await db.calendar_events.find(
            {
                "user_id": share["user_id"],
                "start": {"$gte": now.isoformat(), "$lte": end.isoformat()},
            },
            {"_id": 0, "id": 1, "title": 1, "start": 1, "end": 1, "location": 1},
        )
        .sort("start", 1)
        .to_list(200)
    )

    if not share.get("show_titles"):
        events = [{"id": e["id"], "start": e["start"], "end": e["end"], "title": "Busy"} for e in events]

    # Group events by date
    by_date: Dict[str, list] = {}
    for e in events:
        d = e["start"][:10]
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(e)

    return {
        "share": {
            "name": share.get("name", "Availability"),
            "owner_name": owner_name,
            "owner_timezone": owner_tz,
            "days": share.get("days", 7),
            "show_titles": share.get("show_titles", False),
            "created_at": share.get("created_at"),
        },
        "events": events,
        "events_by_date": by_date,
    }


# ── Meeting Booking (Calendly-style) ──


@router.post("/calendar/booking-page")
async def create_booking_page(request: Request):
    """Create a booking page configuration."""
    user = await _require_calendar_user(request)

    body = await request.json()
    token = uuid.uuid4().hex[:16]
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "name": 1, "timezone": 1})

    page_doc = {
        "token": token,
        "user_id": user.user_id,
        "title": body.get("title", "Book a Meeting"),
        "durations": body.get("durations", [30]),
        "available_start": body.get("available_start", 9),
        "available_end": body.get("available_end", 17),
        "buffer_minutes": body.get("buffer_minutes", 10),
        "days_ahead": body.get("days_ahead", 14),
        "owner_name": (user_doc or {}).get("name", "User"),
        "owner_timezone": (user_doc or {}).get("timezone", "UTC"),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.booking_pages.insert_one(page_doc)
    page_doc.pop("_id", None)
    return {"success": True, "page": page_doc}


@router.get("/calendar/booking-pages/{user_id}")
async def list_booking_pages(user_id: str, request: Request):
    """List active booking pages for a user."""
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    pages = (
        await db.booking_pages.find({"user_id": user_id, "active": True}, {"_id": 0}).sort("created_at", -1).to_list(10)
    )
    return {"pages": pages}


@router.delete("/calendar/booking-page/{token}")
async def delete_booking_page(token: str, request: Request):
    """Deactivate a booking page."""
    user = await _require_calendar_user(request)
    result = await db.booking_pages.update_one({"token": token, "user_id": user.user_id}, {"$set": {"active": False}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Booking page not found")
    return {"success": True}


@router.get("/calendar/booking/{token}")
async def get_booking_page(token: str, date: str = ""):
    """Public: get booking page info and available slots for a date. No auth."""
    page = await db.booking_pages.find_one({"token": token, "active": True}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Booking page not found")

    if not date:
        return {"page": page, "slots": []}

    user_id = page["user_id"]
    day_start = f"{date}T00:00:00"
    day_end = f"{date}T23:59:59"
    existing = await db.calendar_events.find(
        {"user_id": user_id, "start": {"$gte": day_start, "$lte": day_end}}, {"_id": 0, "start": 1, "end": 1}
    ).to_list(100)

    busy_ranges = []
    for e in existing:
        try:
            s = datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
            en = datetime.fromisoformat(e["end"].replace("Z", "+00:00"))
            # Ensure timezone-aware
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if en.tzinfo is None:
                en = en.replace(tzinfo=timezone.utc)
            busy_ranges.append((s, en))
        except Exception:
            pass

    avail_start = page.get("available_start", 9)
    avail_end = page.get("available_end", 17)
    buffer = page.get("buffer_minutes", 10)
    durations = page.get("durations", [30])
    default_dur = durations[0] if durations else 30

    slots = []
    current = datetime.fromisoformat(f"{date}T{avail_start:02d}:00:00+00:00")
    end_time = datetime.fromisoformat(f"{date}T{avail_end:02d}:00:00+00:00")
    now = datetime.now(timezone.utc)

    while current + timedelta(minutes=default_dur) <= end_time:
        slot_end = current + timedelta(minutes=default_dur)
        is_past = current < now
        is_busy = any(
            not (slot_end + timedelta(minutes=buffer) <= bs or current >= be + timedelta(minutes=buffer))
            for bs, be in busy_ranges
        )
        if not is_past and not is_busy:
            slots.append({"start": current.isoformat(), "end": slot_end.isoformat(), "duration": default_dur})
        current += timedelta(minutes=30)

    return {"page": page, "slots": slots}


@router.post("/calendar/booking/{token}/book")
async def book_slot(token: str, request: Request):
    """Book a time slot. Requires authenticated user. Supports recurring bookings."""
    # Auth required - only registered users can book
    booker = await get_current_user(request)
    if not booker:
        raise HTTPException(status_code=401, detail="You must be logged in to book a meeting")

    page = await db.booking_pages.find_one({"token": token, "active": True}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Booking page not found")

    body = await request.json()
    guest_name = body.get("name", "").strip() or booker.name
    guest_email = body.get("email", "").strip() or booker.email
    start = body.get("start", "")
    end = body.get("end", "")
    recurrence_type = str(body.get("recurrence_type", "none")).strip().lower()  # none|weekly|biweekly|monthly
    if recurrence_type not in {"none", "weekly", "biweekly", "monthly"}:
        raise HTTPException(status_code=400, detail="Invalid recurrence_type")
    try:
        recurrence_count = int(body.get("recurrence_count", 4))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid recurrence_count") from exc
    recurrence_count = min(max(recurrence_count, 1), 12)  # max 12 occurrences

    if not guest_name or not guest_email or not start or not end:
        raise HTTPException(status_code=400, detail="Name, email, start, and end are required")

    user_id = page["user_id"]

    # Build list of (start, end) pairs for all occurrences
    start_dt = _parse_calendar_dt(start)
    end_dt = _parse_calendar_dt(end)
    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="Booking end time must be after start time")
    duration = end_dt - start_dt

    occurrences = [(start_dt, end_dt)]
    if recurrence_type != "none" and recurrence_count > 1:
        for i in range(1, recurrence_count):
            if recurrence_type == "weekly":
                delta = timedelta(weeks=i)
            elif recurrence_type == "biweekly":
                delta = timedelta(weeks=2 * i)
            elif recurrence_type == "monthly":
                new_start = _add_months_preserving_day(start_dt, i)
                occurrences.append((new_start, new_start + duration))
                continue
            else:
                break
            occurrences.append((start_dt + delta, end_dt + delta))

    series_id = f"series_{uuid.uuid4().hex[:10]}" if len(occurrences) > 1 else None
    is_recurring = len(occurrences) > 1

    # Check conflicts for all occurrences
    for occ_start, occ_end in occurrences:
        existing = await db.calendar_events.find_one(
            {"user_id": user_id, "start": {"$lt": occ_end.isoformat()}, "end": {"$gt": occ_start.isoformat()}},
            {"_id": 0, "id": 1},
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Slot conflict on {occ_start.strftime('%b %d at %H:%M')}. Please try a different time.",
            )

    calendar_id = await _get_selected_calendar_id(user_id)
    service = await _get_google_service(user_id)

    all_bookings = []
    for idx, (occ_start, occ_end) in enumerate(occurrences):
        booking_id = f"booking_{uuid.uuid4().hex[:10]}"
        occ_start_str = occ_start.isoformat()
        occ_end_str = occ_end.isoformat()

        event = {
            "id": booking_id,
            "user_id": user_id,
            "title": f"Meeting with {guest_name}",
            "start": occ_start_str,
            "end": occ_end_str,
            "description": f"Booked by {guest_name} ({guest_email}) via booking link",
            "location": "",
            "notes": f"Guest: {guest_name}\nEmail: {guest_email}",
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 15}]},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "booking",
            "booking_guest": {"name": guest_name, "email": guest_email},
        }
        await db.calendar_events.insert_one({**event})

        if service:
            try:
                g_event = (
                    service.events()
                    .insert(
                        calendarId=calendar_id,
                        body={
                            "summary": f"Meeting with {guest_name}",
                            "start": _format_event_time(occ_start_str),
                            "end": _format_event_time(occ_end_str),
                            "description": f"Booked by {guest_name} ({guest_email})",
                            "attendees": [{"email": guest_email}],
                        },
                    )
                    .execute()
                )
                await db.calendar_events.update_one(
                    {"id": booking_id}, {"$set": {"google_event_id": g_event.get("id"), "source": "google"}}
                )
            except Exception as e:
                logger.error(f"Google sync for booking failed: {e}")

        booking_record = {
            "booking_id": booking_id,
            "token": token,
            "user_id": user_id,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "start": occ_start_str,
            "end": occ_end_str,
            "status": "confirmed",
            "cancel_token": uuid.uuid4().hex[:16],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_recurring": is_recurring,
            "recurrence_type": recurrence_type if is_recurring else "none",
            "series_id": series_id,
            "occurrence_index": idx,
            "total_occurrences": len(occurrences),
        }
        await db.calendar_bookings.insert_one(booking_record)
        booking_record.pop("_id", None)
        all_bookings.append(booking_record)

    # Send one notification summarizing the booking
    notif_msg = f"{guest_name} booked a meeting at {start[:16].replace('T', ' ')}"
    if is_recurring:
        notif_msg = f"{guest_name} booked {len(occurrences)} recurring meetings ({recurrence_type})"
    await _create_and_push_notification(
        {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": "new_booking",
            "title": "New Meeting Booked",
            "body": notif_msg,
            "message": f"{guest_name} ({guest_email}) booked a meeting",
            "action_url": "/calendar",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Send confirmation emails for ALL bookings (recurring or single)
    try:
        for bk in all_bookings:
            await _send_booking_emails(bk, page)
    except Exception as e:
        logger.error(f"Failed to send booking emails: {e}")

    return {
        "success": True,
        "booking": all_bookings[0],
        "all_bookings": all_bookings,
        "is_recurring": is_recurring,
        "series_id": series_id,
        "total_occurrences": len(all_bookings),
    }


@router.get("/calendar/observability/{user_id}")
async def calendar_observability(user_id: str, request: Request):
    """Enterprise observability snapshot for My Agenda (Feature 34)."""
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)

    now = datetime.now(timezone.utc)
    week_ago_iso = (now - timedelta(days=7)).isoformat()
    month_ago_iso = (now - timedelta(days=30)).isoformat()

    total_events = await db.calendar_events.count_documents({"user_id": user_id})
    upcoming_events = await db.calendar_events.count_documents({"user_id": user_id, "start": {"$gte": now.isoformat()}})
    recent_events = (
        await db.calendar_events.find(
            {"user_id": user_id, "start": {"$gte": month_ago_iso}},
            {"_id": 0, "start": 1, "end": 1},
        )
        .sort("start", 1)
        .limit(400)
        .to_list(400)
    )

    conflict_count = 0
    total_minutes_30d = 0
    sorted_ranges = []
    for ev in recent_events:
        try:
            start_dt = _parse_calendar_dt(ev.get("start", ""))
            end_dt = _parse_calendar_dt(ev.get("end", ""))
            if end_dt <= start_dt:
                continue
            sorted_ranges.append((start_dt, end_dt))
            total_minutes_30d += int((end_dt - start_dt).total_seconds() // 60)
        except Exception:
            continue

    sorted_ranges.sort(key=lambda pair: pair[0])
    for idx in range(1, len(sorted_ranges)):
        prev_end = sorted_ranges[idx - 1][1]
        this_start = sorted_ranges[idx][0]
        if this_start < prev_end:
            conflict_count += 1

    bookings_7d = await db.calendar_bookings.count_documents(
        {"user_id": user_id, "created_at": {"$gte": week_ago_iso}}
    )
    booking_pages_active = await db.booking_pages.count_documents({"user_id": user_id, "active": True})

    return {
        "feature": "book-meeting",
        "window": {"events_days": 30, "bookings_days": 7},
        "summary": {
            "total_events": int(total_events),
            "upcoming_events": int(upcoming_events),
            "bookings_last_7d": int(bookings_7d),
            "active_booking_pages": int(booking_pages_active),
            "conflict_events_last_30d": int(conflict_count),
            "scheduled_minutes_last_30d": int(total_minutes_30d),
        },
    }


@router.get("/calendar/bookings/{user_id}")
async def list_bookings(user_id: str, request: Request):
    """List all bookings for a user (host view)."""
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    bookings = await db.calendar_bookings.find({"user_id": user_id}, {"_id": 0}).sort("start", -1).to_list(100)
    return {"bookings": bookings}


@router.post("/calendar/booking/{token}/resend-confirmation")
async def resend_booking_confirmation(token: str, request: Request):
    """Resend booking confirmation email to the guest."""
    user = await _require_calendar_user(request)
    body = await request.json()
    booking_id = body.get("booking_id")
    if not booking_id:
        raise HTTPException(400, "booking_id required")

    booking = await db.calendar_bookings.find_one({"booking_id": booking_id, "token": token}, {"_id": 0})
    if not booking:
        raise HTTPException(404, "Booking not found")
    _assert_user_scope(user.user_id, booking.get("user_id", ""))

    page = await db.booking_pages.find_one({"token": token}, {"_id": 0})
    if not page:
        raise HTTPException(404, "Booking page not found")

    try:
        await _send_booking_emails(booking, page)
        return {"success": True, "message": "Confirmation emails resent"}
    except Exception as e:
        logger.error(f"Resend confirmation failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/calendar/bookings/{booking_id}/cancel")
async def cancel_booking_by_host(booking_id: str, request: Request):
    """Cancel a booking by the host user."""
    user = await _require_calendar_user(request)
    booking = await db.calendar_bookings.find_one({"booking_id": booking_id, "user_id": user.user_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") == "cancelled":
        return {"success": True, "message": "Already cancelled"}
    await db.calendar_bookings.update_one(
        {"booking_id": booking_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_by": "host",
            }
        },
    )
    # Remove calendar event
    await db.calendar_events.delete_one({"id": booking_id})

    # In-app notification for host (self-confirmation)
    await _create_and_push_notification(
        {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "type": "booking_cancelled_by_host",
            "title": "Meeting Cancelled",
            "body": f"You cancelled the meeting with {booking.get('guest_name', 'Guest')} at {booking.get('start', '')[:16].replace('T', ' ')}",
            "message": f"Meeting with {booking.get('guest_name', 'Guest')} cancelled",
            "action_url": "/calendar",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Send cancellation email to guest
    try:
        from utils.email_service import is_email_configured
        from utils.email_service import render_email_logo
        from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

        if is_email_configured() and booking.get("guest_email"):
            os.environ.get("FRONTEND_BASE_URL", "").rstrip("/") or os.environ.get("REACT_APP_BACKEND_URL", "").rstrip(
                "/"
            )
            guest_name = booking.get("guest_name", "Guest")
            host_user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "name": 1})
            host_name = (host_user_doc or {}).get("name", "Host")
            _fmt_email_dt(booking.get("start", ""))
            render_email_logo(variant="calendar")
            from utils.email_service import send_catalog_template
            guest_email_norm = str(booking.get("guest_email") or "").strip().lower()
            cancel_dedupe_key = f"booking_cancelled:{booking_id}:{guest_email_norm}"
            reserved = await reserve_dispatch_once(
                dedupe_key=cancel_dedupe_key,
                event_type="booking_cancelled",
                channel="email",
                recipient=guest_email_norm,
                payload={"booking_id": booking_id, "cancelled_by": "host"},
            )
            if reserved:
                result = await send_catalog_template(
                    recipient_email=booking["guest_email"],
                    template_key="booking_cancelled",
                    recipient_name=guest_name,
                    user_name=guest_name,
                    host_name=host_name,
                    original_date=booking.get("start_time", "TBD"),
                    cancelled_by="Host",
                    dedupe_key=cancel_dedupe_key,
                )
                await mark_dispatch_status(
                    dedupe_key=cancel_dedupe_key,
                    status="sent" if bool(result.get("success")) else "failed",
                    extra={"sent_at": datetime.now(timezone.utc).isoformat()} if bool(result.get("success")) else {"error": str(result.get("error") or "send_failed")[:300]},
                )
                logger.info(f"Cancellation email sent to guest: {booking['guest_email']}")
    except Exception as e:
        logger.error(f"Failed to send cancellation email to guest: {e}")

    return {"success": True, "message": "Booking cancelled"}


@router.get("/calendar/bookings/series/{series_id}")
async def get_series_bookings(series_id: str, request: Request):
    """Get all bookings in a recurring series."""
    user = await _require_calendar_user(request)
    bookings = (
        await db.calendar_bookings.find(
            {"series_id": series_id, "user_id": user.user_id},
            {"_id": 0},
        )
        .sort("start", 1)
        .to_list(50)
    )
    if not bookings:
        raise HTTPException(status_code=404, detail="Series not found")
    return {"series_id": series_id, "bookings": bookings, "total": len(bookings)}


@router.post("/calendar/bookings/series/{series_id}/cancel")
async def cancel_series(series_id: str, request: Request):
    """Cancel all future bookings in a recurring series."""
    user = await _require_calendar_user(request)
    now = datetime.now(timezone.utc).isoformat()
    result = await db.calendar_bookings.update_many(
        {"series_id": series_id, "user_id": user.user_id, "status": "confirmed", "start": {"$gte": now}},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_by": "host",
            }
        },
    )
    # Remove corresponding calendar events
    future_bookings = await db.calendar_bookings.find(
        {"series_id": series_id, "user_id": user.user_id, "status": "cancelled"}, {"_id": 0, "booking_id": 1}
    ).to_list(50)
    for b in future_bookings:
        await db.calendar_events.delete_one({"id": b["booking_id"]})

    return {"success": True, "cancelled_count": result.modified_count}


@router.get("/admin/booking-dashboard")
async def admin_booking_dashboard(request: Request):
    """Admin-only: comprehensive booking analytics dashboard."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    (now - timedelta(days=30)).isoformat()

    # All bookings
    all_bookings = await db.calendar_bookings.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    total = len(all_bookings)
    confirmed = sum(1 for b in all_bookings if b.get("status") != "cancelled")
    cancelled = total - confirmed
    today_bookings = sum(1 for b in all_bookings if b.get("created_at", "") >= today_start)
    week_bookings = sum(1 for b in all_bookings if b.get("created_at", "") >= week_ago)

    # Upcoming (future, not cancelled)
    upcoming = [b for b in all_bookings if b.get("start", "") >= now.isoformat() and b.get("status") != "cancelled"]
    upcoming.sort(key=lambda x: x.get("start", ""))

    # Booking pages
    active_pages = await db.booking_pages.count_documents({"active": True})
    total_pages = await db.booking_pages.count_documents({})

    # Bookings per day (last 14 days)
    daily_counts = {}
    for i in range(14):
        day = (now - timedelta(days=13 - i)).strftime("%Y-%m-%d")
        daily_counts[day] = 0
    for b in all_bookings:
        day = b.get("created_at", "")[:10]
        if day in daily_counts:
            daily_counts[day] += 1
    daily_chart = [{"date": k, "count": v} for k, v in daily_counts.items()]

    # Peak hours (0-23)
    hour_counts = [0] * 24
    for b in all_bookings:
        try:
            h = int(b.get("start", "T12:")[11:13])
            hour_counts[h] += 1
        except Exception:
            pass
    peak_hours = [{"hour": h, "count": c} for h, c in enumerate(hour_counts)]

    # Top hosts
    host_map: dict = {}
    for b in all_bookings:
        uid = b.get("user_id", "")
        if uid not in host_map:
            host_map[uid] = {"user_id": uid, "total": 0, "confirmed": 0, "cancelled": 0}
        host_map[uid]["total"] += 1
        if b.get("status") == "cancelled":
            host_map[uid]["cancelled"] += 1
        else:
            host_map[uid]["confirmed"] += 1
    top_hosts = sorted(host_map.values(), key=lambda x: x["total"], reverse=True)[:10]
    # Enrich with user names
    for h in top_hosts:
        u = await db.users.find_one({"user_id": h["user_id"]}, {"_id": 0, "name": 1, "email": 1})
        if u:
            h["name"] = u.get("name", "Unknown")
            h["email"] = u.get("email", "")

    # Reminder stats
    reminders_sent = sum(1 for b in all_bookings if b.get("reminder_sent"))

    # Cancellation rate
    cancel_rate = round((cancelled / total * 100), 1) if total > 0 else 0
    conversion_rate = round((confirmed / total * 100), 1) if total > 0 else 0

    # Recent bookings (last 20)
    recent = all_bookings[:20]
    for r in recent:
        # Enrich with host name
        u = await db.users.find_one({"user_id": r.get("user_id")}, {"_id": 0, "name": 1})
        r["host_name"] = (u or {}).get("name", "Unknown")

    # Weekly trend sparkline
    weekly_sparkline = [0] * 7
    for i in range(7):
        day = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        weekly_sparkline[i] = daily_counts.get(day, 0)

    return {
        "kpis": {
            "total_bookings": total,
            "confirmed": confirmed,
            "cancelled": cancelled,
            "cancel_rate": cancel_rate,
            "conversion_rate": conversion_rate,
            "today_bookings": today_bookings,
            "week_bookings": week_bookings,
            "active_pages": active_pages,
            "total_pages": total_pages,
            "upcoming_count": len(upcoming),
            "reminders_sent": reminders_sent,
            "weekly_sparkline": weekly_sparkline,
        },
        "daily_chart": daily_chart,
        "peak_hours": peak_hours,
        "top_hosts": top_hosts,
        "recent_bookings": recent,
        "upcoming": upcoming[:10],
    }


# ── Booking Email Confirmations & .ics ──


def _generate_ics(
    title: str, start: str, end: str, description: str, location: str = "", organizer_email: str = ""
) -> str:
    """Generate an .ics calendar file string."""

    def fmt_dt(iso: str) -> str:
        try:
            d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return d.strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            return iso.replace("-", "").replace(":", "").replace(".", "")[:15] + "Z"

    uid = uuid.uuid4().hex
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//RealAICoach//Calendar//EN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}@realaicoach.app\r\n"
        f"DTSTART:{fmt_dt(start)}\r\n"
        f"DTEND:{fmt_dt(end)}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"LOCATION:{location}\r\n"
        f"STATUS:CONFIRMED\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT15M\r\n"
        "ACTION:DISPLAY\r\n"
        "DESCRIPTION:Reminder\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def _fmt_email_dt(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d.strftime("%A, %B %d, %Y at %I:%M %p UTC")
    except Exception:
        return iso


def _booking_email_html(
    guest_name: str,
    host_name: str,
    start: str,
    end: str,
    cancel_url: str,
    reschedule_url: str,
    ics_url: str,
    is_host: bool,
) -> str:
    from utils.email_service import render_email_logo

    pretty_start = _fmt_email_dt(start)
    pretty_end = _fmt_email_dt(end)

    if is_host:
        intro = f"<strong>{guest_name}</strong> has booked a meeting with you."
        subject_line = f"New Booking: {guest_name}"
    else:
        intro = f"Your meeting with <strong>{host_name}</strong> is confirmed!"
        subject_line = f"Booking Confirmed with {host_name}"

    logo_html = render_email_logo(variant="calendar")
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 520px; margin: 0 auto; background: #0F1117; color: #E5E7EB; border-radius: 16px; overflow: hidden;">
      <div style="background: linear-gradient(135deg, #6366F1, #4F46E5); padding: 28px 24px; text-align: center;">
        {logo_html}
        <div style="font-size: 24px; font-weight: 800; color: #fff;">Meeting Confirmed</div>
        <div style="font-size: 13px; color: rgba(255,255,255,0.8); margin-top: 4px;">{subject_line}</div>
      </div>
      <div style="padding: 24px;">
        <p style="color: #D1D5DB; font-size: 14px; line-height: 1.6;">{intro}</p>
        <div style="background: #161822; border-radius: 12px; padding: 18px; margin: 16px 0; border: 1px solid #1E2030;">
          <div style="font-size: 13px; color: #9CA3AF; margin-bottom: 10px;">When</div>
          <div style="font-size: 14px; font-weight: 700; color: #F9FAFB;">{pretty_start}</div>
          <div style="font-size: 12px; color: #6B7280; margin-top: 2px;">to {pretty_end}</div>
          <div style="margin-top: 12px; font-size: 13px; color: #9CA3AF;">
            With: <strong style="color: #E5E7EB;">{"guest " + guest_name if is_host else host_name}</strong>
          </div>
        </div>
        <div style="text-align: center; margin-top: 20px;">
          <a href="{ics_url}" style="display: inline-block; padding: 10px 24px; border-radius: 10px; background: #10B981; color: #fff; font-size: 13px; font-weight: 700; text-decoration: none; margin-right: 8px;">Add to Calendar</a>
          <a href="{cancel_url}" style="display: inline-block; padding: 10px 24px; border-radius: 10px; background: #EF4444; color: #fff; font-size: 13px; font-weight: 700; text-decoration: none;">Cancel Meeting</a>
        </div>
        <div style="text-align: center; margin-top: 10px;">
          <a href="{reschedule_url}" style="display: inline-block; padding: 10px 24px; border-radius: 10px; background: #6366F1; color: #fff; font-size: 13px; font-weight: 700; text-decoration: none;">Reschedule</a>
        </div>
        <p style="color: #4B5563; font-size: 11px; text-align: center; margin-top: 24px;">
          Powered by RealAICoach Calendar
        </p>
      </div>
    </div>
    """


async def _send_booking_emails(booking: dict, page: dict):
    """Send confirmation emails to both host and guest, with full logging."""
    from utils.email_service import is_email_configured

    if not is_email_configured():
        logger.warning("Email not configured — booking emails will NOT be sent!")
        return

    base_url = os.environ.get("FRONTEND_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")

    cancel_url = f"{base_url}/api/calendar/booking/cancel/{booking.get('cancel_token', '')}"
    reschedule_url = f"{base_url}/book/reschedule/{booking.get('cancel_token', '')}"
    ics_url = f"{base_url}/api/calendar/booking/ics/{booking['booking_id']}"

    guest_name = booking.get("guest_name", "Guest")
    guest_email = booking.get("guest_email", "")
    host_name = page.get("owner_name", "Host")
    start = booking.get("start", "")
    end = booking.get("end", "")
    user_id = booking.get("user_id", "")

    # Format dates for text version
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        date_str = start_dt.strftime("%A, %B %d, %Y")
        time_str = f"{start_dt.strftime('%I:%M %p')}"
    except Exception:
        date_str = start[:10] if start else "TBD"
        time_str = start[11:16] if len(start) > 16 else ""

    # Get host email
    host_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    host_email = (host_user or {}).get("email", "")

    ics_content = _generate_ics(
        title=f"Meeting: {guest_name} & {host_name}",
        start=start,
        end=end,
        description="Booked via RealAICoach Calendar",
    )

    # Email to guest — with logging + text fallback
    if guest_email:
        _booking_email_html(
            guest_name, host_name, start, end, cancel_url, reschedule_url, ics_url, is_host=False
        )
        try:
            from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status
            from utils.email_service import send_catalog_template
            guest_norm = str(guest_email).strip().lower()
            guest_dedupe_key = f"booking_created:{booking['booking_id']}:{guest_norm}"
            guest_reserved = await reserve_dispatch_once(
                dedupe_key=guest_dedupe_key,
                event_type="booking_created",
                channel="email",
                recipient=guest_norm,
                payload={"booking_id": booking["booking_id"], "role": "guest", "host_name": host_name},
            )
            if guest_reserved:
                result = await send_catalog_template(
                    recipient_email=guest_email,
                    template_key="booking_created",
                    recipient_name=guest_name,
                    user_name=guest_name,
                    host_name=host_name,
                    date_str=date_str,
                    dedupe_key=guest_dedupe_key,
                )
                await mark_dispatch_status(
                    dedupe_key=guest_dedupe_key,
                    status="sent" if bool(result.get("success")) else "failed",
                    extra={"sent_at": datetime.now(timezone.utc).isoformat()} if bool(result.get("success")) else {"error": str(result.get("error") or "send_failed")[:300]},
                )
            await db.email_logs.insert_one(
                {
                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "recipient": guest_email,
                    "email_type": "booking_confirmation",
                    "subject": f"Meeting Confirmed with {host_name}",
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"booking_id": booking["booking_id"], "role": "guest"},
                }
            )
            logger.info(f"Booking confirmation sent to guest: {guest_email} (booking={booking['booking_id']})")
        except Exception as e:
            await db.email_logs.insert_one(
                {
                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "recipient": guest_email,
                    "email_type": "booking_confirmation",
                    "subject": f"Meeting Confirmed with {host_name}",
                    "status": "failed",
                    "error": str(e),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"booking_id": booking["booking_id"], "role": "guest"},
                }
            )
            logger.error(f"FAILED to email guest {guest_email}: {e}")

        # Also create in-app notification for guest if they're a registered user
        guest_user = await db.users.find_one(
            {"email": {"$regex": f"^{guest_email}$", "$options": "i"}}, {"_id": 0, "user_id": 1}
        )
        if guest_user:
            await _create_and_push_notification(
                {
                    "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": guest_user["user_id"],
                    "type": "booking_confirmed_guest",
                    "title": f"Meeting Confirmed with {host_name}",
                    "body": f"Your meeting on {date_str} at {time_str} has been confirmed.",
                    "action_url": "/calendar",
                    "read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    # Email to host — with logging + text fallback (add delay to avoid Resend rate limit)
    if host_email:
        await asyncio.sleep(1.2)  # Resend allows 2 req/sec — avoid rate limit
        _booking_email_html(
            guest_name, host_name, start, end, cancel_url, reschedule_url, ics_url, is_host=True
        )
        try:
            from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status
            from utils.email_service import send_catalog_template
            host_norm = str(host_email).strip().lower()
            host_dedupe_key = f"booking_confirmed_host:{booking['booking_id']}:{host_norm}"
            host_reserved = await reserve_dispatch_once(
                dedupe_key=host_dedupe_key,
                event_type="booking_confirmed_host",
                channel="email",
                recipient=host_norm,
                payload={"booking_id": booking["booking_id"], "role": "host", "guest_name": guest_name},
            )
            if host_reserved:
                result = await send_catalog_template(
                    recipient_email=host_email,
                    template_key="booking_confirmed_host",
                    recipient_name=host_name,
                    host_name=host_name,
                    guest_name=guest_name,
                    guest_email=guest_email,
                    date_str=date_str,
                    meeting_type="Coaching Session",
                    dedupe_key=host_dedupe_key,
                )
                await mark_dispatch_status(
                    dedupe_key=host_dedupe_key,
                    status="sent" if bool(result.get("success")) else "failed",
                    extra={"sent_at": datetime.now(timezone.utc).isoformat()} if bool(result.get("success")) else {"error": str(result.get("error") or "send_failed")[:300]},
                )
            await db.email_logs.insert_one(
                {
                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "recipient": host_email,
                    "email_type": "booking_confirmation",
                    "subject": f"New Booking: {guest_name}",
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"booking_id": booking["booking_id"], "role": "host"},
                }
            )
            logger.info(f"Booking notification sent to host: {host_email} (booking={booking['booking_id']})")
        except Exception as e:
            await db.email_logs.insert_one(
                {
                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "recipient": host_email,
                    "email_type": "booking_confirmation",
                    "subject": f"New Booking: {guest_name}",
                    "status": "failed",
                    "error": str(e),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"booking_id": booking["booking_id"], "role": "host"},
                }
            )
            logger.error(f"FAILED to email host {host_email}: {e}")

    # Store .ics for download
    await db.calendar_bookings.update_one(
        {"booking_id": booking["booking_id"]},
        {"$set": {"ics_content": ics_content, "confirmation_sent_at": datetime.now(timezone.utc).isoformat()}},
    )


@router.get("/calendar/booking/cancel/{cancel_token}")
async def cancel_booking(cancel_token: str):
    """Cancel a booking via cancel link (no auth, token-based)."""
    booking = await db.calendar_bookings.find_one({"cancel_token": cancel_token}, {"_id": 0})
    if not booking:
        return Response(
            content=_cancel_page_html("Not Found", "This booking link is invalid or has expired.", False),
            media_type="text/html",
        )

    if booking.get("status") == "cancelled":
        return Response(
            content=_cancel_page_html("Already Cancelled", "This meeting was already cancelled.", False),
            media_type="text/html",
        )

    # Cancel the booking
    await db.calendar_bookings.update_one(
        {"cancel_token": cancel_token},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}},
    )

    # Delete the calendar event
    event = await db.calendar_events.find_one({"id": booking.get("booking_id")}, {"_id": 0})
    if event:
        await db.calendar_events.delete_one({"id": booking["booking_id"]})
        # Try to delete from Google too
        if event.get("google_event_id"):
            try:
                service = await _get_google_service(booking["user_id"])
                calendar_id = await _get_selected_calendar_id(booking["user_id"])
                if service:
                    service.events().delete(calendarId=calendar_id, eventId=event["google_event_id"]).execute()
            except Exception as e:
                logger.error(f"Failed to delete Google event on cancel: {e}")

    # Notify host
    await _create_and_push_notification(
        {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": booking["user_id"],
            "type": "booking_cancelled",
            "title": "Meeting Cancelled",
            "body": f"{booking.get('guest_name', 'Guest')} cancelled the meeting at {booking.get('start', '')[:16].replace('T', ' ')}",
            "message": f"{booking.get('guest_name', 'Guest')} cancelled",
            "action_url": "/calendar",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    guest_name = booking.get("guest_name", "Guest")
    start_str = _fmt_email_dt(booking.get("start", ""))
    return Response(
        content=_cancel_page_html(
            "Meeting Cancelled", f"The meeting with {guest_name} on {start_str} has been cancelled successfully.", True
        ),
        media_type="text/html",
    )


def _cancel_page_html(title: str, message: str, success: bool) -> str:
    color = "#10B981" if success else "#EF4444"
    icon = "&#10003;" if success else "&#10007;"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - RealAICoach</title>
<style>
body{{margin:0;padding:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0F1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#E5E7EB}}
.card{{text-align:center;padding:40px;border-radius:20px;background:#161822;border:1px solid #1E2030;max-width:400px;width:90%}}
.icon{{width:56px;height:56px;border-radius:28px;background:{color}18;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:28px;color:{color}}}
h1{{font-size:20px;font-weight:800;color:{color};margin:0 0 8px}}
p{{font-size:14px;color:#9CA3AF;line-height:1.6;margin:0}}
</style></head>
<body><div class="card"><div class="icon">{icon}</div><h1>{title}</h1><p>{message}</p></div></body></html>"""


# ── Guest Self-Service Reschedule ──


@router.get("/calendar/booking/reschedule/{cancel_token}")
async def get_reschedule_info(cancel_token: str, date: str = ""):
    """Public: get booking info and available slots for rescheduling."""
    booking = await db.calendar_bookings.find_one({"cancel_token": cancel_token}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    if booking.get("status") == "rescheduled":
        raise HTTPException(status_code=400, detail="Booking was already rescheduled")

    # Get the booking page for slot availability
    page = await db.booking_pages.find_one({"token": booking.get("token"), "active": True}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Booking page no longer available")

    result = {
        "booking": {
            "booking_id": booking["booking_id"],
            "guest_name": booking.get("guest_name", ""),
            "guest_email": booking.get("guest_email", ""),
            "start": booking.get("start", ""),
            "end": booking.get("end", ""),
            "status": booking.get("status", "confirmed"),
        },
        "page": page,
        "slots": [],
    }

    if not date:
        return result

    # Calculate available slots (same logic as get_booking_page)
    user_id = page["user_id"]
    day_start = f"{date}T00:00:00"
    day_end = f"{date}T23:59:59"
    existing = await db.calendar_events.find(
        {"user_id": user_id, "start": {"$gte": day_start, "$lte": day_end}}, {"_id": 0, "start": 1, "end": 1}
    ).to_list(100)

    busy_ranges = []
    for e in existing:
        try:
            s = datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
            en = datetime.fromisoformat(e["end"].replace("Z", "+00:00"))
            # Exclude the current booking's event from busy ranges (allow rebooking same slot)
            if e.get("id") != booking["booking_id"]:
                busy_ranges.append((s, en))
        except Exception:
            pass

    avail_start = page.get("available_start", 9)
    avail_end = page.get("available_end", 17)
    buffer = page.get("buffer_minutes", 10)
    durations = page.get("durations", [30])
    default_dur = durations[0] if durations else 30

    slots = []
    current = datetime.fromisoformat(f"{date}T{avail_start:02d}:00:00+00:00")
    end_time = datetime.fromisoformat(f"{date}T{avail_end:02d}:00:00+00:00")
    now = datetime.now(timezone.utc)

    while current + timedelta(minutes=default_dur) <= end_time:
        slot_end = current + timedelta(minutes=default_dur)
        is_past = current < now
        is_busy = any(
            not (slot_end + timedelta(minutes=buffer) <= bs or current >= be + timedelta(minutes=buffer))
            for bs, be in busy_ranges
        )
        if not is_past and not is_busy:
            slots.append({"start": current.isoformat(), "end": slot_end.isoformat(), "duration": default_dur})
        current += timedelta(minutes=30)

    result["slots"] = slots
    return result


@router.post("/calendar/booking/reschedule/{cancel_token}")
async def reschedule_booking(cancel_token: str, request: Request):
    """Public: reschedule a booking to a new time. No auth required."""
    body = await request.json()
    new_start = body.get("start")
    new_end = body.get("end")
    if not new_start or not new_end:
        raise HTTPException(status_code=400, detail="start and end required")

    booking = await db.calendar_bookings.find_one({"cancel_token": cancel_token}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    if booking.get("status") == "rescheduled":
        raise HTTPException(status_code=400, detail="Booking was already rescheduled")

    page = await db.booking_pages.find_one({"token": booking.get("token"), "active": True}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Booking page no longer available")

    old_start = booking.get("start", "")
    user_id = booking["user_id"]
    guest_name = booking.get("guest_name", "Guest")
    guest_email = booking.get("guest_email", "")

    # Cancel old booking
    await db.calendar_bookings.update_one(
        {"cancel_token": cancel_token},
        {"$set": {"status": "rescheduled", "rescheduled_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Delete old calendar event
    await db.calendar_events.delete_one({"id": booking["booking_id"]})

    # Create new booking
    new_booking_id = f"booking_{uuid.uuid4().hex[:10]}"
    new_cancel_token = uuid.uuid4().hex[:16]

    new_event = {
        "id": new_booking_id,
        "user_id": user_id,
        "title": f"Meeting with {guest_name}",
        "start": new_start,
        "end": new_end,
        "type": "booking",
        "source": "booking",
        "description": f"Rescheduled by {guest_name} ({guest_email})",
    }
    await db.calendar_events.insert_one({**new_event})

    # Google sync
    calendar_id = await _get_selected_calendar_id(user_id)
    service = await _get_google_service(user_id)
    if service:
        try:
            # Delete old google event
            old_event = await db.calendar_events.find_one({"id": booking["booking_id"]}, {"_id": 0})
            if old_event and old_event.get("google_event_id"):
                service.events().delete(calendarId=calendar_id, eventId=old_event["google_event_id"]).execute()
            # Create new
            g_event = (
                service.events()
                .insert(
                    calendarId=calendar_id,
                    body={
                        "summary": f"Meeting with {guest_name}",
                        "start": _format_event_time(new_start),
                        "end": _format_event_time(new_end),
                        "description": f"Rescheduled by {guest_name}",
                        "attendees": [{"email": guest_email}] if guest_email else [],
                    },
                )
                .execute()
            )
            await db.calendar_events.update_one(
                {"id": new_booking_id}, {"$set": {"google_event_id": g_event.get("id"), "source": "google"}}
            )
        except Exception as e:
            logger.error(f"Google sync for reschedule failed: {e}")

    new_booking_record = {
        "booking_id": new_booking_id,
        "token": booking.get("token"),
        "user_id": user_id,
        "guest_name": guest_name,
        "guest_email": guest_email,
        "start": new_start,
        "end": new_end,
        "status": "confirmed",
        "cancel_token": new_cancel_token,
        "rescheduled_from": booking["booking_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calendar_bookings.insert_one(new_booking_record)
    new_booking_record.pop("_id", None)

    # Notify host
    old_dt = _fmt_email_dt(old_start)
    new_dt = _fmt_email_dt(new_start)
    await _create_and_push_notification(
        {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": "booking_rescheduled",
            "title": "Meeting Rescheduled",
            "body": f"{guest_name} rescheduled from {old_dt} to {new_dt}",
            "message": f"{guest_name} rescheduled their meeting",
            "action_url": "/calendar",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Send confirmation emails for new booking
    try:
        await _send_booking_emails(new_booking_record, page)
    except Exception as e:
        logger.error(f"Failed to send reschedule confirmation emails: {e}")

    return {"success": True, "booking": new_booking_record}


async def download_ics(booking_id: str):
    """Download .ics file for a booking."""
    booking = await db.calendar_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    ics = booking.get("ics_content")
    if not ics:
        page = await db.booking_pages.find_one({"token": booking.get("token")}, {"_id": 0})
        host_name = (page or {}).get("owner_name", "Host")
        ics = _generate_ics(
            title=f"Meeting: {booking.get('guest_name', 'Guest')} & {host_name}",
            start=booking.get("start", ""),
            end=booking.get("end", ""),
            description="Booked via RealAICoach Calendar",
        )

    from fastapi.responses import Response as ICSResponse

    return ICSResponse(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=meeting-{booking_id}.ics"},
    )


# ── Meeting Reminder Emails ──


def _reminder_email_html(
    guest_name: str, host_name: str, start: str, end: str, cancel_url: str, ics_url: str, is_host: bool
) -> str:
    from utils.email_service import render_email_logo

    pretty_start = _fmt_email_dt(start)
    pretty_end = _fmt_email_dt(end)
    who = guest_name if is_host else host_name
    logo_html = render_email_logo(variant="calendar")
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 520px; margin: 0 auto; background: #0F1117; color: #E5E7EB; border-radius: 16px; overflow: hidden;">
      <div style="background: linear-gradient(135deg, #F59E0B, #D97706); padding: 28px 24px; text-align: center;">
        {logo_html}
        <div style="font-size: 24px; font-weight: 800; color: #fff;">Meeting Starting Soon</div>
        <div style="font-size: 13px; color: rgba(255,255,255,0.85); margin-top: 4px;">15 minute reminder</div>
      </div>
      <div style="padding: 24px;">
        <p style="color: #D1D5DB; font-size: 14px; line-height: 1.6;">
          Your meeting with <strong>{who}</strong> starts in <strong style="color: #F59E0B;">15 minutes</strong>.
        </p>
        <div style="background: #161822; border-radius: 12px; padding: 18px; margin: 16px 0; border: 1px solid #1E2030;">
          <div style="font-size: 13px; color: #9CA3AF; margin-bottom: 10px;">When</div>
          <div style="font-size: 14px; font-weight: 700; color: #F9FAFB;">{pretty_start}</div>
          <div style="font-size: 12px; color: #6B7280; margin-top: 2px;">to {pretty_end}</div>
          <div style="margin-top: 12px; font-size: 13px; color: #9CA3AF;">
            With: <strong style="color: #E5E7EB;">{who}</strong>
          </div>
        </div>
        <div style="text-align: center; margin-top: 20px;">
          <a href="{ics_url}" style="display: inline-block; padding: 10px 24px; border-radius: 10px; background: #10B981; color: #fff; font-size: 13px; font-weight: 700; text-decoration: none; margin-right: 8px;">Open Calendar</a>
          <a href="{cancel_url}" style="display: inline-block; padding: 10px 24px; border-radius: 10px; background: #EF4444; color: #fff; font-size: 13px; font-weight: 700; text-decoration: none;">Cancel Meeting</a>
        </div>
        <p style="color: #4B5563; font-size: 11px; text-align: center; margin-top: 24px;">
          Powered by RealAICoach Calendar
        </p>
      </div>
    </div>
    """


async def send_booking_reminders():
    """Send multi-tier booking reminders: 24h, 1h, and 15min before meetings."""
    from utils.email_service import is_email_configured

    if not is_email_configured():
        return

    now = datetime.now(timezone.utc)
    base_url = os.environ.get("FRONTEND_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

    # Reminder tiers: (label, min_min_before, max_min_before, flag_name, subject_prefix)
    # NOTE: tier windows still drive in-app timing, but EMAIL channel is now strictly
    # one-send-per-booking-per-recipient (global anti-repeat policy).
    tiers = [
        ("24h", 1410, 1470, "reminder_24h_sent", "Tomorrow"),
        ("1h", 50, 75, "reminder_1h_sent", "In 1 Hour"),
        ("15m", 5, 20, "reminder_15m_sent", "Starting Soon"),
    ]

    total_sent = 0

    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status

    async def _email_enabled_for_user(uid: str) -> bool:
        settings = await db.notification_settings.find_one({"user_id": uid}, {"_id": 0, "email_enabled": 1})
        if not settings:
            return True
        return bool(settings.get("email_enabled", True))
    for label, min_min, max_min, flag, subject_prefix in tiers:
        window_start = (now + timedelta(minutes=min_min)).isoformat()
        window_end = (now + timedelta(minutes=max_min)).isoformat()

        bookings = await db.calendar_bookings.find(
            {
                "status": {"$ne": "cancelled"},
                flag: {"$ne": True},
                "start": {"$gte": window_start, "$lte": window_end},
            },
            {"_id": 0},
        ).to_list(200)

        for bk in bookings:
            cancel_url = f"{base_url}/api/calendar/booking/cancel/{bk.get('cancel_token', '')}"
            ics_url = f"{base_url}/api/calendar/booking/ics/{bk['booking_id']}"
            guest_name = bk.get("guest_name", "Guest")
            guest_email = bk.get("guest_email", "")
            start = bk.get("start", "")
            end = bk.get("end", "")
            booking_id = bk.get("booking_id", "")
            user_id = bk.get("user_id", "")

            page = await db.booking_pages.find_one({"token": bk.get("token")}, {"_id": 0, "owner_name": 1})
            host_name = (page or {}).get("owner_name", "Host")
            host_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
            host_email = (host_user or {}).get("email", "")

            # Atomic reservation to avoid duplicate sends during scheduler overlap/retries.
            reservation = await db.calendar_bookings.find_one_and_update(
                {
                    "booking_id": booking_id,
                    "status": {"$ne": "cancelled"},
                    flag: {"$ne": True},
                },
                {
                    "$set": {
                        flag: True,
                        f"{flag}_at": now.isoformat(),
                        f"{flag}_reserved_at": now.isoformat(),
                    }
                },
                return_document=False,
            )
            if not reservation:
                continue

            email_enabled = await _email_enabled_for_user(user_id)

            guest_email_normalized = str(guest_email or "").strip().lower()
            host_email_normalized = str(host_email or "").strip().lower()

            # Enforce one-email-per-booking-per-recipient globally across all tiers.
            recipient_single_send_guard = set()

            # Email guest
            if guest_email and email_enabled and guest_email_normalized:
                try:
                    if guest_email_normalized not in recipient_single_send_guard:
                        existing_guest_send = await db.email_logs.find_one(
                            {
                                "recipient": guest_email,
                                "metadata.booking_id": booking_id,
                                "email_type": {"$regex": r"^booking_reminder_"},
                            },
                            {"_id": 0, "log_id": 1},
                        )
                        if existing_guest_send:
                            recipient_single_send_guard.add(guest_email_normalized)
                        else:
                            _reminder_email_html(guest_name, host_name, start, end, cancel_url, ics_url, is_host=False)
                            from utils.email_service import send_catalog_template
                            guest_dedupe_key = f"booking-reminder-single:{booking_id}:{guest_email_normalized}"
                            guest_reserved = await reserve_dispatch_once(
                                dedupe_key=guest_dedupe_key,
                                event_type=f"booking_reminder_{label}",
                                channel="email",
                                recipient=guest_email_normalized,
                                payload={"booking_id": booking_id, "role": "guest", "tier": label},
                            )
                            if not guest_reserved:
                                recipient_single_send_guard.add(guest_email_normalized)
                                continue
                            await send_catalog_template(
                                recipient_email=guest_email,
                                template_key="meeting_reminder",
                                participant_name=guest_name,
                                other_name=host_name,
                                event_time=start.strftime("%I:%M %p") if hasattr(start, "strftime") else str(start),
                                event_date=start.strftime("%B %d, %Y") if hasattr(start, "strftime") else str(start),
                                is_host=False,
                                cancel_url=cancel_url,
                                dedupe_key=guest_dedupe_key,
                                expected_user_id=user_id,
                                enforce_verified_primary=True,
                            )
                            await mark_dispatch_status(
                                dedupe_key=guest_dedupe_key,
                                status="sent",
                                extra={"sent_at": datetime.now(timezone.utc).isoformat()},
                            )
                            await db.email_logs.insert_one(
                                {
                                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                                    "user_id": user_id,
                                    "recipient": guest_email,
                                    "email_type": f"booking_reminder_{label}",
                                    "subject": f"{subject_prefix}: Meeting with {host_name}",
                                    "status": "sent",
                                    "sent_at": datetime.now(timezone.utc).isoformat(),
                                    "metadata": {"booking_id": booking_id, "tier": label, "role": "guest"},
                                }
                            )
                            recipient_single_send_guard.add(guest_email_normalized)
                            logger.info(f"Reminder ({label}) sent to guest {guest_email} for {booking_id}")
                except Exception as e:
                    try:
                        await mark_dispatch_status(
                            dedupe_key=f"booking-reminder-single:{booking_id}:{guest_email_normalized}",
                            status="failed",
                            extra={"error": str(e)[:400]},
                        )
                    except Exception:
                        pass
                    logger.error(f"Reminder ({label}) FAILED for guest {guest_email}: {e}")

            # Email host
            if host_email and email_enabled and host_email_normalized:
                try:
                    if host_email_normalized not in recipient_single_send_guard:
                        existing_host_send = await db.email_logs.find_one(
                            {
                                "recipient": host_email,
                                "metadata.booking_id": booking_id,
                                "email_type": {"$regex": r"^booking_reminder_"},
                            },
                            {"_id": 0, "log_id": 1},
                        )
                        if existing_host_send:
                            recipient_single_send_guard.add(host_email_normalized)
                        else:
                            _reminder_email_html(guest_name, host_name, start, end, cancel_url, ics_url, is_host=True)
                            from utils.email_service import send_catalog_template
                            host_dedupe_key = f"booking-reminder-single:{booking_id}:{host_email_normalized}"
                            host_reserved = await reserve_dispatch_once(
                                dedupe_key=host_dedupe_key,
                                event_type=f"booking_reminder_{label}",
                                channel="email",
                                recipient=host_email_normalized,
                                payload={"booking_id": booking_id, "role": "host", "tier": label},
                            )
                            if not host_reserved:
                                recipient_single_send_guard.add(host_email_normalized)
                                continue
                            await send_catalog_template(
                                recipient_email=host_email,
                                template_key="meeting_reminder",
                                participant_name=host_name,
                                other_name=guest_name,
                                event_time=start.strftime("%I:%M %p") if hasattr(start, "strftime") else str(start),
                                event_date=start.strftime("%B %d, %Y") if hasattr(start, "strftime") else str(start),
                                is_host=True,
                                cancel_url=cancel_url,
                                dedupe_key=host_dedupe_key,
                                expected_user_id=user_id,
                                enforce_verified_primary=True,
                            )
                            await mark_dispatch_status(
                                dedupe_key=host_dedupe_key,
                                status="sent",
                                extra={"sent_at": datetime.now(timezone.utc).isoformat()},
                            )
                            await db.email_logs.insert_one(
                                {
                                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                                    "user_id": user_id,
                                    "recipient": host_email,
                                    "email_type": f"booking_reminder_{label}",
                                    "subject": f"{subject_prefix}: Meeting with {guest_name}",
                                    "status": "sent",
                                    "sent_at": datetime.now(timezone.utc).isoformat(),
                                    "metadata": {"booking_id": booking_id, "tier": label, "role": "host"},
                                }
                            )
                            recipient_single_send_guard.add(host_email_normalized)
                            logger.info(f"Reminder ({label}) sent to host {host_email} for {booking_id}")
                except Exception as e:
                    try:
                        await mark_dispatch_status(
                            dedupe_key=f"booking-reminder-single:{booking_id}:{host_email_normalized}",
                            status="failed",
                            extra={"error": str(e)[:400]},
                        )
                    except Exception:
                        pass
                    logger.error(f"Reminder ({label}) FAILED for host {host_email}: {e}")

            # In-app notification for host
            await _create_and_push_notification(
                {
                    "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "type": f"booking_reminder_{label}",
                    "title": f"{subject_prefix}: Meeting with {guest_name}",
                    "body": f"Your meeting with {guest_name} starts at {start[:16].replace('T', ' ')}",
                    "message": f"Meeting reminder ({label})",
                    "action_url": "/calendar",
                    "read": False,
                    "created_at": now.isoformat(),
                }
            )

            total_sent += 1

    if total_sent:
        logger.info(f"Sent {total_sent} booking reminder(s) across all tiers")


@router.post("/calendar/booking/send-reminders")
async def trigger_reminders_manually(request: Request):
    """Admin-only: manually trigger reminder check for testing."""
    await require_admin(request)
    await send_booking_reminders()
    return {"success": True, "message": "Reminder check completed"}


def _prune_feature34_calendar_routes_from_integrations_router() -> None:
    """Route-level modularization: calendar endpoints are served from dedicated route modules."""
    blocked_prefixes = ("/calendar",)
    blocked_exact = {
        "/integrations/calendar/auth",
        "/oauth/calendar/callback",
        "/admin/booking-dashboard",
    }
    pruned = []
    for route in router.routes:
        path = str(getattr(route, "path", "") or "")
        if path in blocked_exact or path.startswith(blocked_prefixes):
            continue
        pruned.append(route)
    router.routes = pruned


_prune_feature34_calendar_routes_from_integrations_router()
