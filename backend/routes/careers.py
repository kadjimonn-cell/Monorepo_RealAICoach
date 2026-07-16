"""
Careers Hub — public jobs feed + admin CRUD + AI cover-letter suggestion.

Endpoints:
  GET  /api/careers/jobs                       — public (paginated + filterable)
  GET  /api/careers/jobs/{slug}                — public (single role detail)
  GET  /api/careers/facets                     — public (departments, locations, types for filter chips)
  POST /api/careers/apply                      — public (submit an application; role_slug optional for open applications)
  POST /api/careers/ai-suggest-cover-letter    — public (AI 3 variants — requires Emergent LLM Key)
  GET  /api/admin/careers/jobs                 — admin list (includes disabled/draft)
  POST /api/admin/careers/jobs                 — admin create
  PUT  /api/admin/careers/jobs/{slug}          — admin update
  DELETE /api/admin/careers/jobs/{slug}        — admin delete
  POST /api/admin/careers/jobs/seed            — admin re-seed from /app/backend/data/careers_seed.json
  GET  /api/admin/careers/applications         — admin list applications (optional ?role_slug=)
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from routes.db import db, get_current_user, EMERGENT_LLM_KEY
from utils.pdf_v15_filename import build_pdf_v15_filename

logger = logging.getLogger(__name__)
router = APIRouter()

SEED_FILE = Path("/app/backend/data/careers_seed.json")
JOBS_COL = "careers_jobs"
APPS_COL = "careers_applications"
TALENT_NETWORK_COL = "careers_talent_network"
TALENT_NETWORK_DISPATCH_RUNS_COL = "careers_talent_network_dispatch_runs"
TALENT_NETWORK_DISPATCH_EVENTS_COL = "careers_talent_network_dispatch_events"
TALENT_NETWORK_STATE_COL = "careers_talent_network_user_state"
TALENT_NETWORK_REFERRAL_EVENTS_COL = "careers_talent_network_referral_events"
TALENT_NETWORK_IN_APP_REMINDERS_COL = "careers_talent_network_in_app_reminders"
TALENT_NETWORK_REMINDER_EVENTS_COL = "careers_talent_network_reminder_events"
TALENT_NETWORK_SEGMENTS_COL = "careers_talent_network_campaign_segments"
TALENT_NETWORK_CAMPAIGNS_COL = "careers_talent_network_campaigns"
TALENT_NETWORK_CAMPAIGN_RUNS_COL = "careers_talent_network_campaign_runs"
WEEKLY_CAREERS_TEMPLATE_FLAG_KEY = "weekly_careers_job_template_config"


# ── Helpers ──────────────────────────────────────────────────────────────
async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _clean(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (doc or {}).items() if k != "_id"}


async def _ensure_seeded() -> int:
    """Seed DB from the JSON file if empty. Returns number of jobs in collection."""
    count = await db[JOBS_COL].count_documents({})
    if count > 0:
        return count
    try:
        data = json.loads(SEED_FILE.read_text())
    except Exception as e:
        logger.warning(f"[careers] seed file missing or malformed: {e}")
        return 0
    now = datetime.now(timezone.utc).isoformat()
    for i, job in enumerate(data):
        job.setdefault("status", "open")
        job.setdefault("posted_at", now)
        job.setdefault("updated_at", now)
        job.setdefault("job_id", f"job_{job.get('slug', i)}")
    await db[JOBS_COL].insert_many(data)
    try:
        await db[JOBS_COL].create_index("slug", unique=True)
        await db[JOBS_COL].create_index("department")
        await db[JOBS_COL].create_index("status")
    except Exception:
        pass
    logger.info(f"[careers] Seeded {len(data)} jobs from {SEED_FILE}")
    return len(data)


# ── Public: jobs feed ────────────────────────────────────────────────────
@router.get("/careers/jobs")
async def list_jobs(
    request: Request,
    q: str | None = None,
    department: str | None = None,
    location: str | None = None,
    type: str | None = None,
    limit: int = 200,
):
    await _ensure_seeded()
    query: dict[str, Any] = {"status": "open"}
    if department:
        query["department"] = department
    if location:
        query["location"] = location
    if type:
        query["type"] = type
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"department": {"$regex": q, "$options": "i"}},
        ]
    jobs: list[dict[str, Any]] = []
    async for d in db[JOBS_COL].find(query, {"_id": 0}).sort("posted_at", -1).limit(min(limit, 500)):
        jobs.append(d)
    return {"items": jobs, "count": len(jobs)}


@router.get("/careers/jobs/{slug}")
async def get_job(slug: str):
    await _ensure_seeded()
    doc = await db[JOBS_COL].find_one({"slug": slug, "status": "open"}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Role not found or no longer open")
    return doc


@router.get("/careers/facets")
async def get_facets():
    await _ensure_seeded()
    departments: list[str] = []
    locations: list[str] = []
    types: list[str] = []
    async for d in db[JOBS_COL].aggregate([
        {"$match": {"status": "open"}},
        {"$group": {"_id": {"department": "$department", "location": "$location", "type": "$type"}}},
    ]):
        k = d["_id"]
        if k.get("department") and k["department"] not in departments:
            departments.append(k["department"])
        if k.get("location") and k["location"] not in locations:
            locations.append(k["location"])
        if k.get("type") and k["type"] not in types:
            types.append(k["type"])
    total = await db[JOBS_COL].count_documents({"status": "open"})
    return {"departments": sorted(departments), "locations": sorted(locations), "types": sorted(types), "total_open": total}


@router.get("/careers/overview")
async def get_careers_overview():
    """Public careers summary for high-conversion entry points (welcome/footer)."""
    await _ensure_seeded()

    total_open = await db[JOBS_COL].count_documents({"status": "open"})

    departments: list[str] = []
    locations: list[str] = []
    async for item in db[JOBS_COL].aggregate([
        {"$match": {"status": "open"}},
        {"$group": {"_id": {"department": "$department", "location": "$location"}}},
    ]):
        group = item.get("_id") or {}
        dept = str(group.get("department") or "").strip()
        loc = str(group.get("location") or "").strip()
        if dept and dept not in departments:
            departments.append(dept)
        if loc and loc not in locations:
            locations.append(loc)

    featured_roles: list[dict[str, Any]] = []
    async for role in db[JOBS_COL].find(
        {"status": "open"},
        {
            "_id": 0,
            "slug": 1,
            "title": 1,
            "department": 1,
            "location": 1,
            "type": 1,
            "level": 1,
            "posted_at": 1,
        },
    ).sort("posted_at", -1).limit(4):
        featured_roles.append(role)

    return {
        "total_open": total_open,
        "department_count": len(departments),
        "location_count": len(locations),
        "departments": sorted(departments),
        "locations": sorted(locations),
        "featured_roles": featured_roles,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class TalentNetworkJoinPayload(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)
    role_interests: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_types: list[str] = Field(default_factory=list)
    alert_frequency: Literal["daily", "weekly"] = "weekly"
    reminder_channels: list[Literal["in_app", "email"]] = Field(default_factory=lambda: ["in_app", "email"])
    quiet_hours_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end_hour: int | None = Field(default=None, ge=0, le=23)
    consent_marketing: bool = False
    source: str = Field(default="careers_hub", max_length=80)
    ref: str | None = Field(default=None, max_length=120)


class TalentNetworkPreferencesPayload(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)
    role_interests: list[str] | None = Field(default=None)
    locations: list[str] | None = Field(default=None)
    work_types: list[str] | None = Field(default=None)
    alert_frequency: Literal["daily", "weekly"] | None = None
    reminder_channels: list[Literal["in_app", "email"]] | None = Field(default=None)
    quiet_hours_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end_hour: int | None = Field(default=None, ge=0, le=23)
    consent_marketing: bool | None = None


class TalentNetworkCheckInPayload(BaseModel):
    email: EmailStr
    action: Literal["daily_visit", "save_match", "share", "apply", "profile_update"] = "daily_visit"
    source: str = Field(default="talent_network_hub", max_length=80)


class TalentNetworkReferralSharePayload(BaseModel):
    email: EmailStr
    channel: Literal["whatsapp", "x", "linkedin", "copy_link"] = "copy_link"
    source: str = Field(default="talent_network_hub", max_length=80)
    target: str | None = Field(default=None, max_length=120)


class TalentNetworkReferralAcceptPayload(BaseModel):
    referral_code: str = Field(min_length=4, max_length=40)
    candidate_email: EmailStr | None = None
    source: str = Field(default="talent_network_hub", max_length=80)


class TalentNetworkReminderActionPayload(BaseModel):
    email: EmailStr
    action: Literal["snooze", "resume"] = "snooze"
    snooze_hours: int = Field(default=6, ge=1, le=72)
    note: str | None = Field(default=None, max_length=240)


class TalentNetworkCampaignInteractionPayload(BaseModel):
    email: EmailStr
    campaign_id: str = Field(min_length=4, max_length=80)
    interaction: Literal["open", "click"] = "open"
    channel: Literal["in_app", "email"] = "in_app"
    source: str = Field(default="talent_network_timeline", max_length=80)
    cta_path: str | None = Field(default=None, max_length=180)


class TalentNetworkSegmentUpsertPayload(BaseModel):
    segment_id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=220)
    alert_frequency: Literal["any", "daily", "weekly"] = "any"
    reminder_channel: Literal["any", "in_app", "email"] = "any"
    profile_min: int = Field(default=0, ge=0, le=100)
    profile_max: int = Field(default=100, ge=0, le=100)
    premium_state: Literal["any", "locked", "unlocked"] = "any"
    marketing_consent_required: bool = False
    active: bool = True


class TalentNetworkCampaignCreatePayload(BaseModel):
    campaign_name: str = Field(min_length=3, max_length=140)
    segment_id: str = Field(min_length=4, max_length=80)
    channel: Literal["in_app", "email"] = "in_app"
    schedule_type: Literal["run_now", "scheduled"] = "run_now"
    scheduled_at: str | None = None
    message_title: str = Field(min_length=3, max_length=160)
    message_body: str = Field(min_length=12, max_length=1200)
    cta_label: str | None = Field(default=None, max_length=60)
    cta_path: str | None = Field(default=None, max_length=180)


def _normalize_string_list(values: list[str], *, max_items: int = 12, max_len: int = 80) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        val = str(raw or "").strip()
        if not val:
            continue
        if len(val) > max_len:
            val = val[:max_len]
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
        if len(out) >= max_items:
            break
    return out


def _parse_window_days(raw: int | None, *, default: int = 30) -> int:
    try:
        days = int(raw if raw is not None else default)
    except Exception:
        days = default
    return max(1, min(days, 180))


def _to_bucket_key(text: str) -> str:
    cleaned = str(text or "").strip().lower()
    return cleaned or "unknown"


def _normalize_alert_frequency(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw == "daily":
        return "daily"
    return "weekly"


def _normalize_reminder_channels(values: list[str] | None) -> list[str]:
    allowed = {"in_app", "email"}
    out: list[str] = []
    for raw in values or []:
        key = str(raw or "").strip().lower()
        if key in allowed and key not in out:
            out.append(key)
    if not out:
        return ["in_app", "email"]
    return out


def _compute_profile_completeness(
    *,
    full_name: str,
    role_interests: list[str],
    locations: list[str],
    work_types: list[str],
    reminder_channels: list[str],
    quiet_hours_start_hour: int | None,
    quiet_hours_end_hour: int | None,
) -> int:
    score = 0
    if str(full_name or "").strip():
        score += 20
    if role_interests:
        score += 20
    if locations:
        score += 20
    if work_types:
        score += 20
    if reminder_channels:
        score += 10
    if (quiet_hours_start_hour is not None) and (quiet_hours_end_hour is not None):
        score += 10
    return min(100, max(0, score))


def _build_momentum_summary(state: dict[str, Any] | None) -> dict[str, Any]:
    s = state or {}
    current_streak = int(s.get("current_streak") or 0)
    longest_streak = int(s.get("longest_streak") or 0)
    total_checkins = int(s.get("total_checkins") or 0)
    challenge_progress = int(s.get("challenge_progress") or 0)
    challenge_target = int(s.get("challenge_target") or 5)
    challenge_target = max(1, challenge_target)
    challenge_pct = round(min(100.0, (challenge_progress / challenge_target) * 100.0), 1)

    next_milestone = 3
    for mark in [3, 7, 14, 30, 60, 100]:
        if current_streak < mark:
            next_milestone = mark
            break
        next_milestone = mark

    return {
        "current_streak": current_streak,
        "longest_streak": max(longest_streak, current_streak),
        "total_checkins": total_checkins,
        "challenge": {
            "target": challenge_target,
            "progress": challenge_progress,
            "progress_pct": challenge_pct,
        },
        "next_milestone": next_milestone,
        "remaining_to_milestone": max(0, next_milestone - current_streak),
    }


def _estimate_match_score(job: dict[str, Any], role_interests: list[str], locations: list[str], work_types: list[str]) -> tuple[int, list[str]]:
    title = str(job.get("title") or "").lower()
    department = str(job.get("department") or "").lower()
    location = str(job.get("location") or "").lower()
    job_type = str(job.get("type") or "").lower()

    score = 40
    reasons: list[str] = []

    if role_interests:
        if any((k in title) or (k in department) for k in role_interests):
            score += 25
            reasons.append("Role interests matched")
        else:
            score -= 8
    else:
        reasons.append("General role discovery")

    if locations:
        if any(k in location for k in locations):
            score += 20
            reasons.append("Location preference matched")
        else:
            score -= 6

    if work_types:
        if any(k in job_type for k in work_types):
            score += 15
            reasons.append("Work type preference matched")
        else:
            score -= 5

    final_score = min(99, max(5, score))
    if final_score >= 80:
        reasons.append("High fit opportunity")
    elif final_score >= 60:
        reasons.append("Strong potential fit")
    else:
        reasons.append("Exploratory opportunity")
    return final_score, reasons[:3]


def _safe_parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _compute_next_reminder_eta_iso(reminder_doc: dict[str, Any], now: datetime) -> str:
    snoozed_until_dt = _safe_parse_iso_datetime(reminder_doc.get("snoozed_until"))
    if snoozed_until_dt and snoozed_until_dt > now:
        return snoozed_until_dt.isoformat()

    scheduled_at_dt = _safe_parse_iso_datetime(reminder_doc.get("next_scheduled_at"))
    if scheduled_at_dt and scheduled_at_dt > now:
        return scheduled_at_dt.isoformat()

    alert_frequency = _normalize_alert_frequency(str(reminder_doc.get("alert_frequency") or "weekly"))
    delta = timedelta(days=1) if alert_frequency == "daily" else timedelta(days=7)
    return (now + delta).isoformat()


def _is_hour_within_quiet_window(hour: int, quiet_start: int | None, quiet_end: int | None) -> bool:
    if quiet_start is None or quiet_end is None:
        return False
    start = max(0, min(23, int(quiet_start)))
    end = max(0, min(23, int(quiet_end)))
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _event_within_quiet_hours(created_at_iso: str | None, quiet_start: int | None, quiet_end: int | None) -> bool:
    dt = _safe_parse_iso_datetime(created_at_iso)
    if not dt:
        return False
    return _is_hour_within_quiet_window(int(dt.hour), quiet_start, quiet_end)


def _rate_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


async def _build_talent_network_segment_candidate_query(segment_doc: dict[str, Any]) -> dict[str, Any]:
    profile_min = max(0, min(100, int(segment_doc.get("profile_min") or 0)))
    profile_max = max(profile_min, min(100, int(segment_doc.get("profile_max") or 100)))

    state_query: dict[str, Any] = {
        "profile_completeness": {"$gte": profile_min, "$lte": profile_max},
    }
    premium_state = str(segment_doc.get("premium_state") or "any").strip().lower()
    if premium_state == "unlocked":
        state_query["premium_unlocked"] = True
    elif premium_state == "locked":
        state_query["premium_unlocked"] = False

    state_emails: list[str] = []
    async for row in db[TALENT_NETWORK_STATE_COL].find(state_query, {"_id": 0, "email": 1}).limit(15000):
        email = str(row.get("email") or "").strip().lower()
        if email:
            state_emails.append(email)

    if not state_emails:
        return {"email": "__no_match__"}

    member_query: dict[str, Any] = {
        "email": {"$in": state_emails},
        "$or": [{"status": "active"}, {"status": {"$exists": False}}],
    }

    alert_frequency = str(segment_doc.get("alert_frequency") or "any").strip().lower()
    if alert_frequency in {"daily", "weekly"}:
        member_query["alert_frequency"] = alert_frequency

    reminder_channel = str(segment_doc.get("reminder_channel") or "any").strip().lower()
    if reminder_channel in {"in_app", "email"}:
        member_query["reminder_channels"] = reminder_channel

    if bool(segment_doc.get("marketing_consent_required") or False):
        member_query["consent_marketing"] = True

    return member_query


async def _compute_talent_network_segment_count(segment_doc: dict[str, Any]) -> int:
    query = await _build_talent_network_segment_candidate_query(segment_doc)
    return int(await db[TALENT_NETWORK_COL].count_documents(query))


async def _ensure_talent_network_frequency_defaults() -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db[TALENT_NETWORK_COL].update_many(
        {
            "$or": [
                {"alert_frequency": {"$exists": False}},
                {"alert_frequency": None},
                {"alert_frequency": ""},
            ]
        },
        {
            "$set": {
                "alert_frequency": "weekly",
                "updated_at": now_iso,
            }
        },
    )
    return int(getattr(result, "modified_count", 0) or 0)


@router.post("/careers/talent-network/join")
async def join_talent_network(payload: TalentNetworkJoinPayload):
    email = str(payload.email).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    role_interests = _normalize_string_list(payload.role_interests)
    locations = _normalize_string_list(payload.locations)
    work_types = _normalize_string_list(payload.work_types)
    source = str(payload.source or "careers_hub").strip()[:80] or "careers_hub"
    ref = str(payload.ref or "").strip()[:120]
    full_name = str(payload.full_name or "").strip()[:120]
    alert_frequency = _normalize_alert_frequency(payload.alert_frequency)
    reminder_channels = _normalize_reminder_channels(payload.reminder_channels)
    quiet_hours_start_hour = payload.quiet_hours_start_hour
    quiet_hours_end_hour = payload.quiet_hours_end_hour
    consent_marketing = bool(payload.consent_marketing)
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = await db[TALENT_NETWORK_COL].find_one({"email": email}, {"_id": 0, "network_id": 1})
    already_joined = bool(existing)
    network_id = str((existing or {}).get("network_id") or f"tn_{uuid.uuid4().hex[:12]}")

    doc = {
        "network_id": network_id,
        "email": email,
        "full_name": full_name,
        "role_interests": role_interests,
        "locations": locations,
        "work_types": work_types,
        "alert_frequency": alert_frequency,
        "reminder_channels": reminder_channels,
        "quiet_hours_start_hour": quiet_hours_start_hour,
        "quiet_hours_end_hour": quiet_hours_end_hour,
        "consent_marketing": consent_marketing,
        "source": source,
        "ref": ref,
        "status": "active",
        "updated_at": now_iso,
    }

    if already_joined:
        await db[TALENT_NETWORK_COL].update_one({"email": email}, {"$set": doc})
    else:
        await db[TALENT_NETWORK_COL].insert_one({**doc, "created_at": now_iso})

    existing_state = await db[TALENT_NETWORK_STATE_COL].find_one(
        {"email": email},
        {
            "_id": 0,
            "current_streak": 1,
            "longest_streak": 1,
            "total_checkins": 1,
            "challenge_progress": 1,
            "challenge_target": 1,
            "premium_unlocked": 1,
            "referral_points": 1,
            "referral_code": 1,
        },
    )
    profile_completeness = _compute_profile_completeness(
        full_name=full_name,
        role_interests=role_interests,
        locations=locations,
        work_types=work_types,
        reminder_channels=reminder_channels,
        quiet_hours_start_hour=quiet_hours_start_hour,
        quiet_hours_end_hour=quiet_hours_end_hour,
    )
    referral_code = f"tn_{secrets.token_urlsafe(6).replace('-', '').replace('_', '').lower()[:10]}"
    if existing_state and str(existing_state.get("referral_code") or "").strip():
        referral_code = str(existing_state.get("referral_code") or "").strip()

    await db[TALENT_NETWORK_STATE_COL].update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "network_id": network_id,
                "profile_completeness": profile_completeness,
                "last_active_at": now_iso,
                "referral_code": referral_code,
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "current_streak": 1,
                "longest_streak": 1,
                "total_checkins": 1,
                "challenge_progress": 1,
                "challenge_target": 5,
                "premium_unlocked": False,
                "referral_points": 0,
                "created_at": now_iso,
            },
        },
        upsert=True,
    )

    await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "reminder_channels": reminder_channels,
                "alert_frequency": alert_frequency,
                "quiet_hours_start_hour": quiet_hours_start_hour,
                "quiet_hours_end_hour": quiet_hours_end_hour,
                "last_digest_sent_at": None,
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "created_at": now_iso,
            },
        },
        upsert=True,
    )

    # Keep newsletter pipeline in sync for role-alert outbound readiness.
    existing_newsletter = await db.newsletter_subscribers.find_one(
        {"email": email},
        {"_id": 0, "status": 1, "subscription_type": 1, "categories": 1},
    )
    if not existing_newsletter:
        await db.newsletter_subscribers.insert_one({
            "email": email,
            "status": "active",
            "source": "careers_talent_network",
            "subscription_type": "platform",
            "categories": ["Company News", "Industry Insights", "Enterprise"],
            "subscribed_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        })
    else:
        categories = existing_newsletter.get("categories") or []
        if not isinstance(categories, list):
            categories = []
        merged_categories = _normalize_string_list([
            *categories,
            "Company News",
            "Industry Insights",
            "Enterprise",
        ], max_items=8)
        set_payload = {
            "status": "active",
            "updated_at": now_iso,
            "categories": merged_categories,
        }
        sub_type = str(existing_newsletter.get("subscription_type") or "platform")
        if sub_type == "blog":
            set_payload["subscription_type"] = "all"
        await db.newsletter_subscribers.update_one({"email": email}, {"$set": set_payload})

    return {
        "success": True,
        "already_joined": already_joined,
        "network_id": network_id,
        "message": "You're in the Talent Network. We'll send role alerts that match your preferences.",
        "preferences": {
            "role_interests": role_interests,
            "locations": locations,
            "work_types": work_types,
            "alert_frequency": alert_frequency,
            "reminder_channels": reminder_channels,
            "quiet_hours_start_hour": quiet_hours_start_hour,
            "quiet_hours_end_hour": quiet_hours_end_hour,
            "consent_marketing": consent_marketing,
        },
        "value": {
            "profile_completeness": profile_completeness,
            "referral_code": referral_code,
            "premium_unlocked": bool((existing_state or {}).get("premium_unlocked") or False),
        },
    }


@router.put("/careers/talent-network/preferences")
async def update_talent_network_preferences(payload: TalentNetworkPreferencesPayload):
    email = str(payload.email).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    existing = await db[TALENT_NETWORK_COL].find_one({"email": email}, {"_id": 0, "network_id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    update_doc: dict[str, Any] = {
        "updated_at": now_iso,
    }
    if payload.full_name is not None:
        update_doc["full_name"] = str(payload.full_name or "").strip()[:120]
    if payload.role_interests is not None:
        update_doc["role_interests"] = _normalize_string_list(payload.role_interests)
    if payload.locations is not None:
        update_doc["locations"] = _normalize_string_list(payload.locations)
    if payload.work_types is not None:
        update_doc["work_types"] = _normalize_string_list(payload.work_types)
    if payload.alert_frequency is not None:
        update_doc["alert_frequency"] = _normalize_alert_frequency(payload.alert_frequency)
    if payload.reminder_channels is not None:
        update_doc["reminder_channels"] = _normalize_reminder_channels(payload.reminder_channels)
    if payload.quiet_hours_start_hour is not None:
        update_doc["quiet_hours_start_hour"] = int(payload.quiet_hours_start_hour)
    if payload.quiet_hours_end_hour is not None:
        update_doc["quiet_hours_end_hour"] = int(payload.quiet_hours_end_hour)
    if payload.consent_marketing is not None:
        update_doc["consent_marketing"] = bool(payload.consent_marketing)

    await db[TALENT_NETWORK_COL].update_one({"email": email}, {"$set": update_doc})

    profile = await db[TALENT_NETWORK_COL].find_one(
        {"email": email},
        {
            "_id": 0,
            "network_id": 1,
            "email": 1,
            "full_name": 1,
            "role_interests": 1,
            "locations": 1,
            "work_types": 1,
            "alert_frequency": 1,
            "reminder_channels": 1,
            "quiet_hours_start_hour": 1,
            "quiet_hours_end_hour": 1,
            "consent_marketing": 1,
            "updated_at": 1,
        },
    )

    safe_profile = profile or {}
    profile_completeness = _compute_profile_completeness(
        full_name=str(safe_profile.get("full_name") or ""),
        role_interests=list(safe_profile.get("role_interests") or []),
        locations=list(safe_profile.get("locations") or []),
        work_types=list(safe_profile.get("work_types") or []),
        reminder_channels=_normalize_reminder_channels(list(safe_profile.get("reminder_channels") or [])),
        quiet_hours_start_hour=safe_profile.get("quiet_hours_start_hour"),
        quiet_hours_end_hour=safe_profile.get("quiet_hours_end_hour"),
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    await db[TALENT_NETWORK_STATE_COL].update_one(
        {"email": email},
        {
            "$set": {
                "profile_completeness": profile_completeness,
                "last_active_at": now_iso,
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "email": email,
                "current_streak": 0,
                "longest_streak": 0,
                "total_checkins": 0,
                "challenge_progress": 0,
                "challenge_target": 5,
                "premium_unlocked": False,
                "referral_points": 0,
                "created_at": now_iso,
            },
        },
        upsert=True,
    )

    await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "reminder_channels": _normalize_reminder_channels(list(safe_profile.get("reminder_channels") or [])),
                "alert_frequency": _normalize_alert_frequency(str(safe_profile.get("alert_frequency") or "weekly")),
                "quiet_hours_start_hour": safe_profile.get("quiet_hours_start_hour"),
                "quiet_hours_end_hour": safe_profile.get("quiet_hours_end_hour"),
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "last_digest_sent_at": None,
            },
        },
        upsert=True,
    )

    return {
        "success": True,
        "profile": safe_profile,
        "value": {
            "profile_completeness": profile_completeness,
        },
    }


@router.get("/careers/talent-network/hub")
async def get_talent_network_hub(email: str):
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required")

    member = await db[TALENT_NETWORK_COL].find_one(
        {"email": normalized_email},
        {
            "_id": 0,
            "network_id": 1,
            "email": 1,
            "full_name": 1,
            "role_interests": 1,
            "locations": 1,
            "work_types": 1,
            "alert_frequency": 1,
            "reminder_channels": 1,
            "quiet_hours_start_hour": 1,
            "quiet_hours_end_hour": 1,
            "consent_marketing": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    )
    if not member:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    state = await db[TALENT_NETWORK_STATE_COL].find_one(
        {"email": normalized_email},
        {
            "_id": 0,
            "profile_completeness": 1,
            "current_streak": 1,
            "longest_streak": 1,
            "total_checkins": 1,
            "challenge_progress": 1,
            "challenge_target": 1,
            "referral_points": 1,
            "premium_unlocked": 1,
            "referral_code": 1,
            "last_active_at": 1,
            "last_checkin_date": 1,
        },
    )

    role_interests = _normalize_string_list(list(member.get("role_interests") or []), max_items=8)
    locations = _normalize_string_list(list(member.get("locations") or []), max_items=6)
    work_types = _normalize_string_list(list(member.get("work_types") or []), max_items=4)

    ranked_matches: list[dict[str, Any]] = []
    async for job in db[JOBS_COL].find(
        {"status": "open"},
        {"_id": 0, "slug": 1, "title": 1, "department": 1, "location": 1, "type": 1, "level": 1, "posted_at": 1},
    ).sort("posted_at", -1).limit(80):
        score, reasons = _estimate_match_score(job, [s.lower() for s in role_interests], [s.lower() for s in locations], [s.lower() for s in work_types])
        ranked_matches.append({
            "slug": str(job.get("slug") or ""),
            "title": str(job.get("title") or ""),
            "department": str(job.get("department") or ""),
            "location": str(job.get("location") or ""),
            "type": str(job.get("type") or ""),
            "level": str(job.get("level") or ""),
            "posted_at": str(job.get("posted_at") or ""),
            "match_score": score,
            "match_reasons": reasons,
        })
    ranked_matches.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    top_matches = ranked_matches[:8]

    reminder_state = await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].find_one(
        {"email": normalized_email},
        {"_id": 0, "last_digest_sent_at": 1, "updated_at": 1},
    )

    recent_referrals = int(await db[TALENT_NETWORK_REFERRAL_EVENTS_COL].count_documents({"referrer_email": normalized_email}))
    momentum = _build_momentum_summary(state)

    return {
        "success": True,
        "member": member,
        "state": {
            "profile_completeness": int((state or {}).get("profile_completeness") or _compute_profile_completeness(
                full_name=str(member.get("full_name") or ""),
                role_interests=role_interests,
                locations=locations,
                work_types=work_types,
                reminder_channels=_normalize_reminder_channels(list(member.get("reminder_channels") or [])),
                quiet_hours_start_hour=member.get("quiet_hours_start_hour"),
                quiet_hours_end_hour=member.get("quiet_hours_end_hour"),
            )),
            "referral_code": str((state or {}).get("referral_code") or ""),
            "referral_points": int((state or {}).get("referral_points") or 0),
            "premium_unlocked": bool((state or {}).get("premium_unlocked") or False),
            "recent_referrals": recent_referrals,
            "momentum": momentum,
        },
        "top_matches": top_matches,
        "premium": {
            "is_unlocked": bool((state or {}).get("premium_unlocked") or False),
            "teaser": {
                "advanced_fit_insights": True,
                "priority_alert_window": True,
                "weekly_shortlist_digest": True,
            },
        },
        "reminder_state": reminder_state or {"last_digest_sent_at": None},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/careers/talent-network/check-in")
async def talent_network_check_in(payload: TalentNetworkCheckInPayload):
    email = str(payload.email).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    member = await db[TALENT_NETWORK_COL].find_one({"email": email}, {"_id": 0, "email": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    today = now.date()

    state = await db[TALENT_NETWORK_STATE_COL].find_one({"email": email}, {"_id": 0}) or {}
    last_checkin_raw = str(state.get("last_checkin_date") or "")
    previous_date = None
    if last_checkin_raw:
        try:
            previous_date = datetime.fromisoformat(last_checkin_raw).date()
        except Exception:
            previous_date = None

    current_streak = int(state.get("current_streak") or 0)
    if previous_date == today:
        pass
    elif previous_date and (today - previous_date).days == 1:
        current_streak += 1
    else:
        current_streak = 1

    longest_streak = max(int(state.get("longest_streak") or 0), current_streak)
    total_checkins = int(state.get("total_checkins") or 0)
    if previous_date != today:
        total_checkins += 1

    challenge_target = int(state.get("challenge_target") or 5)
    challenge_progress = int(state.get("challenge_progress") or 0)
    if previous_date != today:
        challenge_progress = min(challenge_target, challenge_progress + 1)

    await db[TALENT_NETWORK_STATE_COL].update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "last_checkin_date": today.isoformat(),
                "last_active_at": now_iso,
                "current_streak": current_streak,
                "longest_streak": longest_streak,
                "total_checkins": total_checkins,
                "challenge_progress": challenge_progress,
                "challenge_target": challenge_target,
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "referral_points": 0,
                "premium_unlocked": False,
            },
        },
        upsert=True,
    )

    reminder_doc = await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].find_one(
        {"email": email},
        {"_id": 0, "alert_frequency": 1},
    ) or {}
    next_scheduled_at = _compute_next_reminder_eta_iso(reminder_doc, now)
    await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "next_scheduled_at": next_scheduled_at,
                "last_action": payload.action,
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "alert_frequency": "weekly",
                "reminder_channels": ["in_app", "email"],
            },
        },
        upsert=True,
    )

    await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
        {
            "event_id": f"tn_rem_{uuid.uuid4().hex[:12]}",
            "email": email,
            "event_type": "check_in",
            "action": payload.action,
            "source": str(payload.source or "talent_network_hub")[:80],
            "created_at": now_iso,
        }
    )

    return {
        "success": True,
        "action": payload.action,
        "momentum": _build_momentum_summary({
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "total_checkins": total_checkins,
            "challenge_progress": challenge_progress,
            "challenge_target": challenge_target,
        }),
        "updated_at": now_iso,
    }


@router.get("/careers/talent-network/reminder-timeline")
async def get_talent_network_reminder_timeline(email: str):
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required")

    member = await db[TALENT_NETWORK_COL].find_one({"email": normalized_email}, {"_id": 0, "email": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    now = datetime.now(timezone.utc)
    reminder_doc = await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].find_one(
        {"email": normalized_email},
        {
            "_id": 0,
            "email": 1,
            "alert_frequency": 1,
            "reminder_channels": 1,
            "quiet_hours_start_hour": 1,
            "quiet_hours_end_hour": 1,
            "last_digest_sent_at": 1,
            "next_scheduled_at": 1,
            "snoozed_until": 1,
            "last_action": 1,
            "updated_at": 1,
        },
    ) or {
        "email": normalized_email,
        "alert_frequency": "weekly",
        "reminder_channels": ["in_app", "email"],
        "quiet_hours_start_hour": None,
        "quiet_hours_end_hour": None,
        "last_digest_sent_at": None,
        "next_scheduled_at": None,
        "snoozed_until": None,
        "last_action": "none",
        "updated_at": now.isoformat(),
    }

    next_eta = _compute_next_reminder_eta_iso(reminder_doc, now)
    history: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_REMINDER_EVENTS_COL].find(
        {"email": normalized_email},
        {
            "_id": 0,
            "event_id": 1,
            "event_type": 1,
            "action": 1,
            "channel": 1,
            "campaign_id": 1,
            "campaign_name": 1,
            "meta": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(25):
        history.append(row)

    return {
        "success": True,
        "timeline": {
            "email": normalized_email,
            "alert_frequency": _normalize_alert_frequency(str(reminder_doc.get("alert_frequency") or "weekly")),
            "reminder_channels": _normalize_reminder_channels(list(reminder_doc.get("reminder_channels") or [])),
            "quiet_hours_start_hour": reminder_doc.get("quiet_hours_start_hour"),
            "quiet_hours_end_hour": reminder_doc.get("quiet_hours_end_hour"),
            "next_reminder_eta": next_eta,
            "snoozed_until": reminder_doc.get("snoozed_until"),
            "last_digest_sent_at": reminder_doc.get("last_digest_sent_at"),
            "last_action": str(reminder_doc.get("last_action") or "none"),
            "updated_at": reminder_doc.get("updated_at"),
            "history": history,
        },
    }


@router.post("/careers/talent-network/reminder-action")
async def post_talent_network_reminder_action(payload: TalentNetworkReminderActionPayload):
    email = str(payload.email).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    member = await db[TALENT_NETWORK_COL].find_one({"email": email}, {"_id": 0, "email": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    action = str(payload.action or "snooze").strip().lower()

    reminder_doc = await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].find_one(
        {"email": email},
        {"_id": 0, "alert_frequency": 1, "snoozed_until": 1, "next_scheduled_at": 1},
    ) or {"alert_frequency": "weekly"}

    update_doc: dict[str, Any] = {
        "email": email,
        "last_action": action,
        "updated_at": now_iso,
    }
    if action == "snooze":
        snooze_until_iso = (now + timedelta(hours=int(payload.snooze_hours))).isoformat()
        update_doc["snoozed_until"] = snooze_until_iso
        update_doc["next_scheduled_at"] = snooze_until_iso
    else:
        update_doc["snoozed_until"] = None
        update_doc["next_scheduled_at"] = _compute_next_reminder_eta_iso(reminder_doc, now)

    await db[TALENT_NETWORK_IN_APP_REMINDERS_COL].update_one(
        {"email": email},
        {
            "$set": update_doc,
            "$setOnInsert": {
                "created_at": now_iso,
                "alert_frequency": "weekly",
                "reminder_channels": ["in_app", "email"],
            },
        },
        upsert=True,
    )

    await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
        {
            "event_id": f"tn_rem_{uuid.uuid4().hex[:12]}",
            "email": email,
            "event_type": "timeline_action",
            "action": action,
            "meta": {
                "snooze_hours": int(payload.snooze_hours),
                "note": str(payload.note or "")[:240],
            },
            "created_at": now_iso,
        }
    )

    return {
        "success": True,
        "action": action,
        "snoozed_until": update_doc.get("snoozed_until"),
        "next_reminder_eta": update_doc.get("next_scheduled_at"),
        "updated_at": now_iso,
    }


@router.post("/careers/talent-network/campaign-interaction")
async def post_talent_network_campaign_interaction(payload: TalentNetworkCampaignInteractionPayload):
    email = str(payload.email).strip().lower()
    campaign_id = str(payload.campaign_id or "").strip().lower()
    interaction = str(payload.interaction or "open").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not campaign_id:
        raise HTTPException(status_code=400, detail="campaign_id is required")
    if interaction not in {"open", "click"}:
        raise HTTPException(status_code=400, detail="interaction must be open or click")

    member = await db[TALENT_NETWORK_COL].find_one(
        {"email": email},
        {
            "_id": 0,
            "email": 1,
            "quiet_hours_start_hour": 1,
            "quiet_hours_end_hour": 1,
        },
    )
    if not member:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    campaign = await db[TALENT_NETWORK_CAMPAIGNS_COL].find_one(
        {"campaign_id": campaign_id},
        {
            "_id": 0,
            "campaign_id": 1,
            "campaign_name": 1,
            "segment_id": 1,
            "segment_name": 1,
            "channel": 1,
        },
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    dedupe_since_iso = (now - timedelta(seconds=30)).isoformat()
    duplicate = await db[TALENT_NETWORK_REMINDER_EVENTS_COL].find_one(
        {
            "email": email,
            "campaign_id": campaign_id,
            "event_type": "campaign_engagement",
            "action": interaction,
            "created_at": {"$gte": dedupe_since_iso},
        },
        {"_id": 0, "event_id": 1},
    )
    if duplicate:
        return {
            "success": True,
            "tracked": False,
            "reason": "duplicate_within_window",
            "campaign_id": campaign_id,
            "interaction": interaction,
        }

    is_quiet = _is_hour_within_quiet_window(
        int(now.hour),
        member.get("quiet_hours_start_hour"),
        member.get("quiet_hours_end_hour"),
    )
    event_id = f"tn_rem_{uuid.uuid4().hex[:12]}"
    await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
        {
            "event_id": event_id,
            "email": email,
            "event_type": "campaign_engagement",
            "action": interaction,
            "channel": str(payload.channel or campaign.get("channel") or "in_app").strip().lower(),
            "campaign_id": campaign_id,
            "campaign_name": str(campaign.get("campaign_name") or ""),
            "segment_id": str(campaign.get("segment_id") or ""),
            "segment_name": str(campaign.get("segment_name") or ""),
            "meta": {
                "source": str(payload.source or "talent_network_timeline")[:80],
                "cta_path": str(payload.cta_path or "")[:180],
                "quiet_hours": bool(is_quiet),
            },
            "created_at": now_iso,
        }
    )

    return {
        "success": True,
        "tracked": True,
        "event_id": event_id,
        "campaign_id": campaign_id,
        "interaction": interaction,
        "quiet_hours": bool(is_quiet),
    }


@router.post("/careers/talent-network/referral/share")
async def talent_network_referral_share(payload: TalentNetworkReferralSharePayload):
    email = str(payload.email).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    member = await db[TALENT_NETWORK_COL].find_one({"email": email}, {"_id": 0, "network_id": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Talent Network profile not found")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    cooldown_since = (now - timedelta(minutes=2)).isoformat()

    recent = await db[TALENT_NETWORK_REFERRAL_EVENTS_COL].find_one(
        {
            "referrer_email": email,
            "channel": payload.channel,
            "event_type": "share",
            "created_at": {"$gte": cooldown_since},
        },
        {"_id": 0, "event_id": 1, "created_at": 1},
    )
    if recent:
        return {
            "success": False,
            "cooldown": True,
            "message": "Please wait before sharing again on the same channel.",
            "next_retry_after_seconds": 120,
        }

    state = await db[TALENT_NETWORK_STATE_COL].find_one({"email": email}, {"_id": 0, "referral_code": 1, "referral_points": 1}) or {}
    referral_code = str(state.get("referral_code") or "").strip()
    if not referral_code:
        referral_code = f"tn_{secrets.token_urlsafe(6).replace('-', '').replace('_', '').lower()[:10]}"
        await db[TALENT_NETWORK_STATE_COL].update_one({"email": email}, {"$set": {"referral_code": referral_code, "updated_at": now_iso}}, upsert=True)

    event_id = f"tn_ref_{uuid.uuid4().hex[:12]}"
    await db[TALENT_NETWORK_REFERRAL_EVENTS_COL].insert_one(
        {
            "event_id": event_id,
            "event_type": "share",
            "referrer_email": email,
            "referral_code": referral_code,
            "channel": payload.channel,
            "target": str(payload.target or "").strip()[:120],
            "source": str(payload.source or "talent_network_hub")[:80],
            "created_at": now_iso,
        }
    )

    frontend_base = "/careers?intent=talent-network"
    share_link = f"{frontend_base}&referral={referral_code}&ref=talent-network-share"
    preview_text = "I joined RealAICoach Talent Network for smarter role matches. Join with my invite link."

    return {
        "success": True,
        "event_id": event_id,
        "referral_code": referral_code,
        "channel": payload.channel,
        "share_preview": {
            "title": "Join my Talent Network invite",
            "text": preview_text,
            "link": share_link,
        },
    }


@router.post("/careers/talent-network/referral/accept")
async def talent_network_referral_accept(payload: TalentNetworkReferralAcceptPayload):
    referral_code = str(payload.referral_code or "").strip().lower()
    if not referral_code:
        raise HTTPException(status_code=400, detail="Referral code is required")

    referrer_state = await db[TALENT_NETWORK_STATE_COL].find_one(
        {"referral_code": referral_code},
        {"_id": 0, "email": 1, "referral_points": 1, "premium_unlocked": 1},
    )
    if not referrer_state:
        raise HTTPException(status_code=404, detail="Referral code not found")

    referrer_email = str(referrer_state.get("email") or "").strip().lower()
    candidate_email = str(payload.candidate_email or "").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    duplicate = await db[TALENT_NETWORK_REFERRAL_EVENTS_COL].find_one(
        {
            "event_type": "accept",
            "referral_code": referral_code,
            "candidate_email": candidate_email,
        },
        {"_id": 0, "event_id": 1},
    )
    if duplicate:
        return {
            "success": True,
            "already_counted": True,
            "referrer_email": referrer_email,
        }

    event_id = f"tn_refacc_{uuid.uuid4().hex[:12]}"
    await db[TALENT_NETWORK_REFERRAL_EVENTS_COL].insert_one(
        {
            "event_id": event_id,
            "event_type": "accept",
            "referral_code": referral_code,
            "referrer_email": referrer_email,
            "candidate_email": candidate_email,
            "source": str(payload.source or "talent_network_hub")[:80],
            "created_at": now_iso,
        }
    )

    next_points = int(referrer_state.get("referral_points") or 0) + 1
    premium_unlocked = bool(referrer_state.get("premium_unlocked") or False)
    if next_points >= 3:
        premium_unlocked = True

    await db[TALENT_NETWORK_STATE_COL].update_one(
        {"email": referrer_email},
        {
            "$set": {
                "referral_points": next_points,
                "premium_unlocked": premium_unlocked,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    return {
        "success": True,
        "event_id": event_id,
        "referrer_email": referrer_email,
        "referral_points": next_points,
        "premium_unlocked": premium_unlocked,
    }


@router.get("/admin/careers/talent-network/overview")
async def admin_talent_network_overview(request: Request, days: int = 30):
    await _require_admin(request)
    await _ensure_talent_network_frequency_defaults()
    window_days = _parse_window_days(days, default=30)
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=window_days)).isoformat()

    total_signups = int(await db[TALENT_NETWORK_COL].count_documents({}))
    active_signups = int(await db[TALENT_NETWORK_COL].count_documents({"status": "active"}))
    signups_in_window = int(await db[TALENT_NETWORK_COL].count_documents({"created_at": {"$gte": since_iso}}))

    role_interest_counts: dict[str, int] = {}
    async for row in db[TALENT_NETWORK_COL].aggregate([
        {"$project": {"_id": 0, "role_interests": {"$ifNull": ["$role_interests", []]}}},
        {"$unwind": {"path": "$role_interests", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$role_interests", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 12},
    ]):
        label = str(row.get("_id") or "").strip()
        if label:
            role_interest_counts[label] = int(row.get("count") or 0)

    source_counts: dict[str, int] = {}
    async for row in db[TALENT_NETWORK_COL].aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        source = str(row.get("_id") or "unknown").strip() or "unknown"
        source_counts[source] = int(row.get("count") or 0)

    source_conversion: list[dict[str, Any]] = []
    for source, signup_count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True):
        click_events = int(
            await db.careers_public_events.count_documents(
                {
                    "created_at": {"$gte": since_iso},
                    "event": {"$in": ["careers_page_view", "careers_filter_used", "careers_apply_click", "talent_network_joined"]},
                    "$or": [
                        {"source": source},
                        {"ref": source},
                    ],
                }
            )
        )
        conversion_rate = round((signup_count / click_events) * 100, 2) if click_events > 0 else 0.0
        source_conversion.append(
            {
                "source": source,
                "signups": signup_count,
                "click_events": click_events,
                "conversion_rate_pct": conversion_rate,
            }
        )

    frequency_breakdown = {
        "daily": 0,
        "weekly": 0,
    }
    async for row in db[TALENT_NETWORK_COL].aggregate([
        {
            "$project": {
                "_id": 0,
                "alert_frequency": {
                    "$ifNull": ["$alert_frequency", "weekly"],
                },
            }
        },
        {"$group": {"_id": "$alert_frequency", "count": {"$sum": 1}}},
    ]):
        key = _normalize_alert_frequency(str(row.get("_id") or "weekly"))
        frequency_breakdown[key] += int(row.get("count") or 0)

    reminder_channel_breakdown = {
        "in_app": 0,
        "email": 0,
    }
    async for row in db[TALENT_NETWORK_COL].aggregate([
        {
            "$project": {
                "_id": 0,
                "reminder_channels": {
                    "$ifNull": ["$reminder_channels", ["in_app", "email"]],
                },
            }
        },
        {"$unwind": {"path": "$reminder_channels", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$reminder_channels", "count": {"$sum": 1}}},
    ]):
        key = str(row.get("_id") or "").strip().lower()
        if key in reminder_channel_breakdown:
            reminder_channel_breakdown[key] += int(row.get("count") or 0)

    premium_unlocked_count = int(await db[TALENT_NETWORK_STATE_COL].count_documents({"premium_unlocked": True}))
    referral_accept_count = int(await db[TALENT_NETWORK_REFERRAL_EVENTS_COL].count_documents({"event_type": "accept", "created_at": {"$gte": since_iso}}))

    latest_run = await db[TALENT_NETWORK_DISPATCH_RUNS_COL].find_one({}, {"_id": 0}, sort=[("started_at", -1)])

    recent_dispatches: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_DISPATCH_EVENTS_COL].find(
        {"created_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "event_id": 1,
            "run_id": 1,
            "email": 1,
            "status": 1,
            "top_job_title": 1,
            "top_job_slug": 1,
            "source": 1,
            "matched_count": 1,
            "alert_frequency": 1,
            "confidence_score": 1,
            "confidence_label": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(20):
        recent_dispatches.append(row)

    dispatch_totals = {
        "attempted": 0,
        "sent": 0,
        "failed": 0,
    }
    confidence_distribution = {
        "high": 0,
        "medium": 0,
        "low": 0,
    }
    confidence_score_total = 0.0
    confidence_score_samples = 0
    async for row in db[TALENT_NETWORK_DISPATCH_RUNS_COL].find(
        {"started_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "attempted": 1,
            "sent": 1,
            "failed": 1,
            "confidence_distribution": 1,
            "confidence_total_score": 1,
            "confidence_samples": 1,
        },
    ):
        dispatch_totals["attempted"] += int(row.get("attempted") or 0)
        dispatch_totals["sent"] += int(row.get("sent") or 0)
        dispatch_totals["failed"] += int(row.get("failed") or 0)
        row_distribution = row.get("confidence_distribution") or {}
        confidence_distribution["high"] += int(row_distribution.get("high") or 0)
        confidence_distribution["medium"] += int(row_distribution.get("medium") or 0)
        confidence_distribution["low"] += int(row_distribution.get("low") or 0)
        confidence_score_total += float(row.get("confidence_total_score") or 0.0)
        confidence_score_samples += int(row.get("confidence_samples") or 0)

    avg_confidence_score = round((confidence_score_total / confidence_score_samples), 2) if confidence_score_samples > 0 else 0.0

    return {
        "window_days": window_days,
        "generated_at": now.isoformat(),
        "summary": {
            "total_signups": total_signups,
            "active_signups": active_signups,
            "signups_in_window": signups_in_window,
            "dispatch_totals": dispatch_totals,
            "frequency_breakdown": frequency_breakdown,
            "reminder_channel_breakdown": reminder_channel_breakdown,
            "premium_unlocked_count": premium_unlocked_count,
            "referral_accept_in_window": referral_accept_count,
            "confidence": {
                "avg_score": avg_confidence_score,
                "distribution": confidence_distribution,
                "sample_size": confidence_score_samples,
            },
        },
        "top_role_interests": [
            {"label": label, "count": count}
            for label, count in role_interest_counts.items()
        ],
        "source_conversion": source_conversion,
        "latest_dispatch_run": latest_run or {},
        "recent_dispatches": recent_dispatches,
    }


@router.get("/admin/careers/talent-network/deliverability-analytics")
async def admin_talent_network_deliverability_analytics(request: Request, days: int = 30, limit: int = 8):
    await _require_admin(request)
    window_days = _parse_window_days(days, default=30)
    safe_limit = max(3, min(int(limit or 8), 40))
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=window_days)).isoformat()

    campaign_map: dict[str, dict[str, Any]] = {}
    async for campaign in db[TALENT_NETWORK_CAMPAIGNS_COL].find(
        {},
        {
            "_id": 0,
            "campaign_id": 1,
            "campaign_name": 1,
            "segment_id": 1,
            "segment_name": 1,
            "channel": 1,
        },
    ).limit(800):
        campaign_id = str(campaign.get("campaign_id") or "").strip().lower()
        if campaign_id:
            campaign_map[campaign_id] = campaign

    sent_events: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_REMINDER_EVENTS_COL].find(
        {
            "event_type": "campaign_delivery",
            "created_at": {"$gte": since_iso},
        },
        {
            "_id": 0,
            "email": 1,
            "campaign_id": 1,
            "campaign_name": 1,
            "segment_id": 1,
            "segment_name": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(60000):
        sent_events.append(row)

    engagement_events: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_REMINDER_EVENTS_COL].find(
        {
            "event_type": "campaign_engagement",
            "action": {"$in": ["open", "click"]},
            "created_at": {"$gte": since_iso},
        },
        {
            "_id": 0,
            "email": 1,
            "campaign_id": 1,
            "campaign_name": 1,
            "segment_id": 1,
            "segment_name": 1,
            "action": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(80000):
        engagement_events.append(row)

    all_emails: set[str] = set()
    for row in sent_events:
        email = str(row.get("email") or "").strip().lower()
        if email:
            all_emails.add(email)
    for row in engagement_events:
        email = str(row.get("email") or "").strip().lower()
        if email:
            all_emails.add(email)

    quiet_map: dict[str, dict[str, Any]] = {}
    if all_emails:
        async for member in db[TALENT_NETWORK_COL].find(
            {"email": {"$in": list(all_emails)}},
            {
                "_id": 0,
                "email": 1,
                "quiet_hours_start_hour": 1,
                "quiet_hours_end_hour": 1,
            },
        ).limit(max(100, len(all_emails) + 20)):
            email = str(member.get("email") or "").strip().lower()
            if email:
                quiet_map[email] = member

    def _segment_bucket(segment_id: str, segment_name: str) -> dict[str, Any]:
        return {
            "segment_id": segment_id,
            "segment_name": segment_name or "Unassigned",
            "sent": 0,
            "opened": 0,
            "clicked": 0,
            "quiet_sent": 0,
            "quiet_opened": 0,
            "quiet_clicked": 0,
            "non_quiet_sent": 0,
            "non_quiet_opened": 0,
            "non_quiet_clicked": 0,
            "campaign_ids": set(),
            "unique_sent_recipients": set(),
            "unique_open_recipients": set(),
            "unique_click_recipients": set(),
        }

    segment_map: dict[str, dict[str, Any]] = {}

    def _resolve_segment(row: dict[str, Any]) -> tuple[str, str]:
        campaign_id = str(row.get("campaign_id") or "").strip().lower()
        campaign = campaign_map.get(campaign_id) or {}
        segment_id = str(row.get("segment_id") or campaign.get("segment_id") or "").strip().lower()
        if not segment_id:
            segment_id = "unassigned"
        segment_name = str(row.get("segment_name") or campaign.get("segment_name") or "Unassigned").strip() or "Unassigned"
        return segment_id, segment_name

    for row in sent_events:
        email = str(row.get("email") or "").strip().lower()
        if not email:
            continue
        segment_id, segment_name = _resolve_segment(row)
        bucket = segment_map.setdefault(segment_id, _segment_bucket(segment_id, segment_name))
        bucket["sent"] += 1
        bucket["unique_sent_recipients"].add(email)
        campaign_id = str(row.get("campaign_id") or "").strip().lower()
        if campaign_id:
            bucket["campaign_ids"].add(campaign_id)

        quiet_cfg = quiet_map.get(email) or {}
        is_quiet = _event_within_quiet_hours(
            row.get("created_at"),
            quiet_cfg.get("quiet_hours_start_hour"),
            quiet_cfg.get("quiet_hours_end_hour"),
        )
        if is_quiet:
            bucket["quiet_sent"] += 1
        else:
            bucket["non_quiet_sent"] += 1

    for row in engagement_events:
        email = str(row.get("email") or "").strip().lower()
        if not email:
            continue
        action = str(row.get("action") or "").strip().lower()
        if action not in {"open", "click"}:
            continue
        segment_id, segment_name = _resolve_segment(row)
        bucket = segment_map.setdefault(segment_id, _segment_bucket(segment_id, segment_name))

        quiet_cfg = quiet_map.get(email) or {}
        is_quiet = _event_within_quiet_hours(
            row.get("created_at"),
            quiet_cfg.get("quiet_hours_start_hour"),
            quiet_cfg.get("quiet_hours_end_hour"),
        )

        if action == "open":
            bucket["opened"] += 1
            bucket["unique_open_recipients"].add(email)
            if is_quiet:
                bucket["quiet_opened"] += 1
            else:
                bucket["non_quiet_opened"] += 1
        elif action == "click":
            bucket["clicked"] += 1
            bucket["unique_click_recipients"].add(email)
            if is_quiet:
                bucket["quiet_clicked"] += 1
            else:
                bucket["non_quiet_clicked"] += 1

    rows: list[dict[str, Any]] = []
    for segment_id, bucket in sorted(segment_map.items(), key=lambda item: int(item[1].get("sent") or 0), reverse=True):
        unique_sent = len(bucket["unique_sent_recipients"])
        unique_open = len(bucket["unique_open_recipients"])
        unique_click = len(bucket["unique_click_recipients"])
        quiet_open_rate = _rate_pct(int(bucket["quiet_opened"]), int(bucket["quiet_sent"]))
        non_quiet_open_rate = _rate_pct(int(bucket["non_quiet_opened"]), int(bucket["non_quiet_sent"]))
        quiet_click_rate = _rate_pct(int(bucket["quiet_clicked"]), int(bucket["quiet_sent"]))
        non_quiet_click_rate = _rate_pct(int(bucket["non_quiet_clicked"]), int(bucket["non_quiet_sent"]))
        rows.append(
            {
                "segment_id": segment_id,
                "segment_name": bucket["segment_name"],
                "campaign_count": len(bucket["campaign_ids"]),
                "sent": int(bucket["sent"]),
                "opened": int(bucket["opened"]),
                "clicked": int(bucket["clicked"]),
                "unique_sent_recipients": unique_sent,
                "unique_open_recipients": unique_open,
                "unique_click_recipients": unique_click,
                "open_rate_pct": _rate_pct(unique_open, unique_sent),
                "click_rate_pct": _rate_pct(unique_click, unique_sent),
                "click_to_open_rate_pct": _rate_pct(unique_click, unique_open),
                "quiet_hours_sent": int(bucket["quiet_sent"]),
                "quiet_hours_opened": int(bucket["quiet_opened"]),
                "quiet_hours_clicked": int(bucket["quiet_clicked"]),
                "quiet_hours_open_rate_pct": quiet_open_rate,
                "non_quiet_open_rate_pct": non_quiet_open_rate,
                "quiet_hours_click_rate_pct": quiet_click_rate,
                "non_quiet_click_rate_pct": non_quiet_click_rate,
                "quiet_hours_impact_pct": round(quiet_open_rate - non_quiet_open_rate, 2),
            }
        )

    total_sent = sum(int(row.get("sent") or 0) for row in rows)
    total_opened = sum(int(row.get("opened") or 0) for row in rows)
    total_clicked = sum(int(row.get("clicked") or 0) for row in rows)
    total_quiet_sent = sum(int(row.get("quiet_hours_sent") or 0) for row in rows)
    total_quiet_opened = sum(int(row.get("quiet_hours_opened") or 0) for row in rows)
    total_quiet_clicked = sum(int(row.get("quiet_hours_clicked") or 0) for row in rows)
    total_non_quiet_sent = max(0, total_sent - total_quiet_sent)
    total_non_quiet_opened = max(0, total_opened - total_quiet_opened)

    summary = {
        "segments_count": len(rows),
        "campaigns_count": len({
            str(row.get("campaign_id") or "").strip().lower()
            for row in sent_events
            if str(row.get("campaign_id") or "").strip()
        }),
        "sent": total_sent,
        "opened": total_opened,
        "clicked": total_clicked,
        "open_rate_pct": _rate_pct(total_opened, total_sent),
        "click_rate_pct": _rate_pct(total_clicked, total_sent),
        "click_to_open_rate_pct": _rate_pct(total_clicked, total_opened),
        "quiet_hours_sent": total_quiet_sent,
        "quiet_hours_opened": total_quiet_opened,
        "quiet_hours_clicked": total_quiet_clicked,
        "quiet_hours_open_rate_pct": _rate_pct(total_quiet_opened, total_quiet_sent),
        "non_quiet_open_rate_pct": _rate_pct(total_non_quiet_opened, total_non_quiet_sent),
        "quiet_hours_impact_pct": round(
            _rate_pct(total_quiet_opened, total_quiet_sent)
            - _rate_pct(total_non_quiet_opened, total_non_quiet_sent),
            2,
        ),
    }

    return {
        "window_days": window_days,
        "generated_at": now.isoformat(),
        "summary": summary,
        "segments": rows[:safe_limit],
    }


@router.post("/admin/careers/talent-network/dispatch/run-now")
async def admin_run_talent_network_dispatch(request: Request, force: bool = False):
    user = await _require_admin(request)
    from scheduler_jobs import scheduled_talent_network_role_alert_dispatch

    result = await scheduled_talent_network_role_alert_dispatch(
        triggered_by=f"manual:{getattr(user, 'email', 'admin')}",
        force=bool(force),
    )
    return {"ok": True, "result": result}


@router.get("/admin/careers/talent-network/segments")
async def admin_list_talent_network_segments(request: Request):
    await _require_admin(request)
    items: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_SEGMENTS_COL].find({}, {"_id": 0}).sort("updated_at", -1).limit(200):
        segment_doc = {
            "segment_id": str(row.get("segment_id") or ""),
            "name": str(row.get("name") or ""),
            "description": str(row.get("description") or ""),
            "alert_frequency": str(row.get("alert_frequency") or "any"),
            "reminder_channel": str(row.get("reminder_channel") or "any"),
            "profile_min": int(row.get("profile_min") or 0),
            "profile_max": int(row.get("profile_max") or 100),
            "premium_state": str(row.get("premium_state") or "any"),
            "marketing_consent_required": bool(row.get("marketing_consent_required") or False),
            "active": bool(row.get("active") if row.get("active") is not None else True),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "updated_by": row.get("updated_by"),
        }
        segment_doc["estimated_members"] = int(await _compute_talent_network_segment_count(segment_doc))
        items.append(segment_doc)
    return {
        "success": True,
        "segments": items,
        "count": len(items),
    }


@router.post("/admin/careers/talent-network/segments")
async def admin_upsert_talent_network_segment(request: Request, payload: TalentNetworkSegmentUpsertPayload):
    user = await _require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    segment_id = str(payload.segment_id or "").strip().lower()
    if not segment_id:
        segment_id = f"tn_seg_{uuid.uuid4().hex[:10]}"

    profile_min = max(0, min(100, int(payload.profile_min)))
    profile_max = max(profile_min, min(100, int(payload.profile_max)))

    doc = {
        "segment_id": segment_id,
        "name": str(payload.name or "").strip()[:120],
        "description": str(payload.description or "").strip()[:220],
        "alert_frequency": str(payload.alert_frequency or "any").strip().lower(),
        "reminder_channel": str(payload.reminder_channel or "any").strip().lower(),
        "profile_min": profile_min,
        "profile_max": profile_max,
        "premium_state": str(payload.premium_state or "any").strip().lower(),
        "marketing_consent_required": bool(payload.marketing_consent_required),
        "active": bool(payload.active),
        "updated_at": now_iso,
        "updated_by": str(getattr(user, "email", "admin") or "admin"),
    }

    await db[TALENT_NETWORK_SEGMENTS_COL].update_one(
        {"segment_id": segment_id},
        {
            "$set": doc,
            "$setOnInsert": {
                "created_at": now_iso,
            },
        },
        upsert=True,
    )

    estimate = int(await _compute_talent_network_segment_count(doc))
    return {
        "success": True,
        "segment": {
            **doc,
            "segment_id": segment_id,
            "created_at": now_iso,
            "estimated_members": estimate,
        },
    }


@router.post("/admin/careers/talent-network/campaigns")
async def admin_create_talent_network_campaign(request: Request, payload: TalentNetworkCampaignCreatePayload):
    user = await _require_admin(request)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    segment = await db[TALENT_NETWORK_SEGMENTS_COL].find_one(
        {"segment_id": str(payload.segment_id or "").strip().lower(), "active": {"$ne": False}},
        {"_id": 0},
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found or inactive")

    schedule_type = str(payload.schedule_type or "run_now").strip().lower()
    scheduled_at = payload.scheduled_at
    if schedule_type == "scheduled":
        parsed = _safe_parse_iso_datetime(scheduled_at)
        if not parsed:
            raise HTTPException(status_code=400, detail="scheduled_at must be a valid ISO datetime")
        if parsed <= now:
            raise HTTPException(status_code=400, detail="scheduled_at must be in the future")
        scheduled_at = parsed.isoformat()
    else:
        scheduled_at = now_iso

    campaign_id = f"tn_cmp_{uuid.uuid4().hex[:12]}"
    campaign_doc = {
        "campaign_id": campaign_id,
        "campaign_name": str(payload.campaign_name or "").strip()[:140],
        "segment_id": str(segment.get("segment_id") or "").strip().lower(),
        "segment_name": str(segment.get("name") or "Segment"),
        "channel": str(payload.channel or "in_app").strip().lower(),
        "schedule_type": schedule_type,
        "scheduled_at": scheduled_at,
        "message_title": str(payload.message_title or "Reminder").strip()[:160],
        "message_body": str(payload.message_body or "").strip()[:1200],
        "cta_label": str(payload.cta_label or "Open Talent Network").strip()[:60],
        "cta_path": str(payload.cta_path or "/talent-network").strip()[:180],
        "status": "scheduled" if schedule_type == "scheduled" else "queued",
        "created_at": now_iso,
        "updated_at": now_iso,
        "created_by": str(getattr(user, "email", "admin") or "admin"),
        "updated_by": str(getattr(user, "email", "admin") or "admin"),
        "segment_snapshot": {
            "alert_frequency": str(segment.get("alert_frequency") or "any"),
            "reminder_channel": str(segment.get("reminder_channel") or "any"),
            "profile_min": int(segment.get("profile_min") or 0),
            "profile_max": int(segment.get("profile_max") or 100),
            "premium_state": str(segment.get("premium_state") or "any"),
            "marketing_consent_required": bool(segment.get("marketing_consent_required") or False),
        },
    }
    await db[TALENT_NETWORK_CAMPAIGNS_COL].insert_one(campaign_doc)
    return {
        "success": True,
        "campaign": _clean(campaign_doc),
    }


@router.get("/admin/careers/talent-network/campaigns")
async def admin_list_talent_network_campaigns(request: Request, limit: int = 60):
    await _require_admin(request)
    safe_limit = max(10, min(int(limit or 60), 200))
    campaigns: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_CAMPAIGNS_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(safe_limit):
        campaigns.append(row)

    recent_runs: list[dict[str, Any]] = []
    async for row in db[TALENT_NETWORK_CAMPAIGN_RUNS_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(50):
        recent_runs.append(row)

    return {
        "success": True,
        "campaigns": campaigns,
        "runs": recent_runs,
    }


@router.post("/admin/careers/talent-network/campaigns/{campaign_id}/run-now")
async def admin_run_talent_network_campaign_now(request: Request, campaign_id: str):
    user = await _require_admin(request)
    normalized_campaign_id = str(campaign_id or "").strip().lower()
    if not normalized_campaign_id:
        raise HTTPException(status_code=400, detail="campaign_id is required")

    campaign = await db[TALENT_NETWORK_CAMPAIGNS_COL].find_one(
        {"campaign_id": normalized_campaign_id},
        {"_id": 0},
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    segment = await db[TALENT_NETWORK_SEGMENTS_COL].find_one(
        {"segment_id": str(campaign.get("segment_id") or "").strip().lower()},
        {"_id": 0},
    )
    if not segment:
        raise HTTPException(status_code=404, detail="Campaign segment not found")

    member_query = await _build_talent_network_segment_candidate_query(segment)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    run_id = f"tn_cmp_run_{uuid.uuid4().hex[:12]}"
    attempted = 0
    sent = 0
    skipped = 0
    failed = 0
    sample_recipients: list[str] = []

    async for member in db[TALENT_NETWORK_COL].find(
        member_query,
        {
            "_id": 0,
            "email": 1,
            "full_name": 1,
            "reminder_channels": 1,
        },
    ).limit(8000):
        attempted += 1
        email = str(member.get("email") or "").strip().lower()
        if not email:
            skipped += 1
            continue

        channels = _normalize_reminder_channels(list(member.get("reminder_channels") or []))
        campaign_channel = str(campaign.get("channel") or "in_app").strip().lower()
        if campaign_channel not in channels:
            skipped += 1
            continue

        if len(sample_recipients) < 12:
            sample_recipients.append(email)

        if campaign_channel == "in_app":
            await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
                {
                    "event_id": f"tn_rem_{uuid.uuid4().hex[:12]}",
                    "email": email,
                    "event_type": "campaign_delivery",
                    "action": "in_app_sent",
                    "channel": "in_app",
                    "campaign_id": normalized_campaign_id,
                    "campaign_name": str(campaign.get("campaign_name") or ""),
                    "segment_id": str(campaign.get("segment_id") or ""),
                    "segment_name": str(campaign.get("segment_name") or ""),
                    "meta": {
                        "title": str(campaign.get("message_title") or ""),
                        "body": str(campaign.get("message_body") or "")[:360],
                        "cta_label": str(campaign.get("cta_label") or "Open Talent Network"),
                        "cta_path": str(campaign.get("cta_path") or "/talent-network"),
                    },
                    "created_at": now_iso,
                }
            )
            sent += 1
            continue

        try:
            from utils.email_service import send_catalog_template
            result = await send_catalog_template(
                recipient_email=email,
                template_key="weekly_careers_job_announcement",
                recipient_name=str(member.get("full_name") or "there").strip() or "there",
                user_name=str(member.get("full_name") or "there").strip() or "there",
                job_title=str(campaign.get("message_title") or "Career Reminder"),
                department="Talent Network",
                location="Remote",
                role_type="Reminder",
                apply_url=str(campaign.get("cta_path") or "/talent-network"),
                careers_url="/talent-network",
                subject_override=str(campaign.get("message_title") or "Talent Network Reminder")[:160],
            )
            if result.get("success"):
                await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
                    {
                        "event_id": f"tn_rem_{uuid.uuid4().hex[:12]}",
                        "email": email,
                        "event_type": "campaign_delivery",
                        "action": "email_sent",
                        "channel": "email",
                        "campaign_id": normalized_campaign_id,
                        "campaign_name": str(campaign.get("campaign_name") or ""),
                        "segment_id": str(campaign.get("segment_id") or ""),
                        "segment_name": str(campaign.get("segment_name") or ""),
                        "meta": {
                            "title": str(campaign.get("message_title") or ""),
                            "subject": str(campaign.get("message_title") or "")[:160],
                        },
                        "created_at": now_iso,
                    }
                )
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    run_doc = {
        "run_id": run_id,
        "campaign_id": normalized_campaign_id,
        "campaign_name": str(campaign.get("campaign_name") or ""),
        "segment_id": str(campaign.get("segment_id") or ""),
        "segment_name": str(campaign.get("segment_name") or ""),
        "channel": str(campaign.get("channel") or "in_app"),
        "attempted": attempted,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "sample_recipients": sample_recipients,
        "triggered_by": str(getattr(user, "email", "admin") or "admin"),
        "created_at": now_iso,
    }
    await db[TALENT_NETWORK_CAMPAIGN_RUNS_COL].insert_one(run_doc)

    await db[TALENT_NETWORK_CAMPAIGNS_COL].update_one(
        {"campaign_id": normalized_campaign_id},
        {
            "$set": {
                "status": "completed",
                "last_run_id": run_id,
                "last_run_at": now_iso,
                "last_run_summary": {
                    "attempted": attempted,
                    "sent": sent,
                    "skipped": skipped,
                    "failed": failed,
                },
                "updated_at": now_iso,
                "updated_by": str(getattr(user, "email", "admin") or "admin"),
            }
        },
    )

    return {
        "success": True,
        "run": _clean(run_doc),
    }


# ── Public: submit application ───────────────────────────────────────────
class ApplicationPayload(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    role_slug: str | None = None  # None → open application
    years_experience: str | None = None
    linkedin: str | None = None
    portfolio: str | None = None
    skills: list[str] | None = None
    cover_letter: str = Field(min_length=10, max_length=8000)
    # Optional: UUID the client generated before uploading attachments.
    # Every attachment uploaded under this token is moved to the new
    # application on successful submit (bind_attachments_to_application).
    draft_token: str | None = Field(default=None, max_length=64)


@router.post("/careers/apply")
async def submit_application(payload: ApplicationPayload):
    if payload.role_slug:
        job = await db[JOBS_COL].find_one({"slug": payload.role_slug}, {"_id": 0, "title": 1})
        if not job:
            raise HTTPException(status_code=404, detail="Role not found")
        role_title = job.get("title")
    else:
        role_title = "Open Application"

    app_id = f"app_{uuid.uuid4().hex[:12]}"

    # Bind any draft attachments BEFORE writing the application doc so the
    # stored metadata stays consistent with what lives on disk. The helper
    # is a no-op when draft_token is empty.
    attachments: list[dict[str, Any]] = []
    try:
        from routes.careers_attachments import bind_attachments_to_application
        attachments = await bind_attachments_to_application(
            draft_token=payload.draft_token, application_id=app_id
        )
    except Exception as _e:  # pragma: no cover — never block the apply flow
        logger.warning(f"[careers] attachment bind skipped: {_e}")

    doc = {
        "application_id": app_id,
        "role_slug": payload.role_slug,
        "role_title": role_title,
        "name": payload.name.strip(),
        "email": payload.email.strip().lower(),
        "phone": (payload.phone or "").strip(),
        "years_experience": (payload.years_experience or "").strip(),
        "linkedin": (payload.linkedin or "").strip(),
        "portfolio": (payload.portfolio or "").strip(),
        "skills": payload.skills or [],
        "cover_letter": payload.cover_letter.strip(),
        "status": "received",
        "attachments": attachments,
        "attachment_count": len(attachments),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[APPS_COL].insert_one(doc)
    logger.info(
        f"[careers] new application {app_id} · role={role_title} · email={doc['email']} · "
        f"attachments={len(attachments)}"
    )
    # Auto-score on ingest (fire-and-forget — never blocks apply flow)
    try:
        import asyncio as _asyncio
        from routes.careers_tier3 import auto_score_on_ingest
        auto_score_task = _asyncio.create_task(auto_score_on_ingest(app_id))
        auto_score_task.add_done_callback(
            lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
        )
    except Exception as _e:
        logger.debug(f"[careers] auto-score dispatch skipped: {_e}")

    # ── V7 transactional emails (fire-and-forget) ──────────────────────
    # 1) Confirmation to the applicant.
    # 2) Notification to hiring@realaicoach.app (careers-only inbox).
    #
    # Channel policy (Apr 22 2026): careers-apply notifications MUST go
    # ONLY to the hiring inbox — not the generic ADMIN_EMAILS (which
    # contains admin@realaicoach.app). Rationale: careers notifications
    # are HR-sensitive (contains applicant PII, salary expectations,
    # resume attachments) and need to land in the dedicated hiring inbox
    # for recruiter workflow. Admin@ is a generic ops inbox — wrong
    # audience, wrong retention, wrong access-control boundary.
    try:
        import asyncio as _asyncio
        import os as _os
        from utils.email_service import is_email_configured, send_catalog_template

        if is_email_configured():
            # Plus-addressed reply target lets applicants reply naturally to
            # the friendly "hiring@realaicoach.app" alias; our MTA delivers
            # any `hiring+*@` back into the hiring inbox, and the inbound
            # webhook correlates the "+APP-XXX" tag to this application.
            hiring_inbox_env = (
                _os.environ.get("CAREERS_HIRING_INBOX", "hiring@realaicoach.app") or ""
            ).strip()
            reply_to_addr = ""
            if "@" in hiring_inbox_env:
                _local, _domain = hiring_inbox_env.split("@", 1)
                reply_to_addr = f"{_local}+{app_id}@{_domain}"

            thread_headers = {
                "X-Application-ID": app_id,
                "X-RAC-Thread": "careers",
            }

            async def _send_applicant_confirmation() -> None:
                try:
                    # Thread-correlation headers + the new `X-Application-ID`
                    # header so Resend webhook ingest can correlate open/click
                    # events back to this applicant via `tags[application_id]`.
                    _headers_with_appid = dict(thread_headers or {})
                    _headers_with_appid["X-Application-ID"] = app_id
                    result = await send_catalog_template(
                        recipient_email=doc["email"],
                        template_key="career_confirmation",
                        recipient_name=doc["name"],
                        applicant_name=doc["name"],
                        position=role_title,
                        application_id=app_id,
                        reply_to=[reply_to_addr] if reply_to_addr else None,
                        headers=_headers_with_appid,
                    )
                    # Persist outbound message into the thread log so future
                    # replies can be resolved via In-Reply-To header lookup.
                    if result and result.get("success"):
                        try:
                            from routes.careers_thread import append_thread_message
                            await append_thread_message(
                                application_id=app_id,
                                direction="outbound",
                                from_email=hiring_inbox_env,
                                to_email=doc["email"],
                                subject=(
                                    f"Application Received — {role_title} at RealAICoach "
                                    f"[{app_id}]"
                                ),
                                body_text="(career_confirmation template)",
                                message_id=result.get("message_id") or "",
                                correlation_signal="outbound_dispatch",
                            )
                        except Exception as _e:  # pragma: no cover
                            logger.warning(
                                f"[careers] thread outbound-log append failed: {_e}"
                            )
                except Exception as _e:  # pragma: no cover
                    logger.warning(f"[careers] applicant confirmation email failed: {_e}")

            applicant_confirmation_task = _asyncio.create_task(_send_applicant_confirmation())
            applicant_confirmation_task.add_done_callback(
                lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
            )

            # Careers channel uses ONLY the hiring inbox — never ADMIN_EMAILS.
            hiring_inbox = hiring_inbox_env

            async def _send_admin_notify(to_email: str) -> None:
                try:
                    await send_catalog_template(
                        recipient_email=to_email,
                        template_key="career_admin_notify",
                        applicant_name=doc["name"],
                        position=role_title,
                        application_id=app_id,
                        email=doc["email"],
                        experience=doc.get("years_experience", ""),
                    )
                except Exception as _e:  # pragma: no cover
                    logger.warning(
                        f"[careers] admin notify email to {to_email} failed: {_e}"
                    )

            if hiring_inbox:
                admin_notify_task = _asyncio.create_task(_send_admin_notify(hiring_inbox))
                admin_notify_task.add_done_callback(
                    lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
                )
    except Exception as _e:  # pragma: no cover — never block apply flow
        logger.warning(f"[careers] email dispatch skipped: {_e}")

    return {
        "success": True,
        "application_id": app_id,
        "role_title": role_title,
        "attachment_count": len(attachments),
    }


# ── Public: Application Tracker ──────────────────────────────────────────
# Lightweight applicant-facing status page. Security model:
#   • `application_id` = 16-char unguessable UUID suffix (post-`app_` prefix)
#   • No authentication required — the token itself is the credential
#   • PII redacted: only first name is returned, never email/phone/resume
#   • Rate-limited (in-mem token bucket) per-IP to thwart enumeration attempts.
_TRACK_RL_BUCKET: dict[str, list[float]] = {}
_TRACK_RL_LIMIT = 30   # requests per window
_TRACK_RL_WINDOW = 60  # seconds

_STATUS_TIMELINE: list[tuple[str, str, str]] = [
    # (key, title, subtitle)
    ("received", "Application Received",
     "We've received your application and it's in the queue for recruiter review."),
    ("screening", "Under Screening",
     "A recruiter is actively reviewing your submission against the role requirements."),
    ("interview", "Interview Stage",
     "We'd like to talk! Expect an email with interview scheduling details shortly."),
    ("offer", "Offer Extended",
     "An offer has been sent to your inbox — please check for next steps."),
    ("hired", "Welcome Aboard",
     "You've accepted. Our team will be in touch about onboarding."),
]


def _rate_limit_tracker(client_ip: str) -> None:
    now = time.time()
    bucket = _TRACK_RL_BUCKET.setdefault(client_ip, [])
    # prune expired entries
    cutoff = now - _TRACK_RL_WINDOW
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= _TRACK_RL_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests — try again in a minute.")
    bucket.append(now)


@router.get("/careers/applications/track/{application_id}")
async def track_application(application_id: str, request: Request):
    """Public applicant-facing tracker for `/careers/track/{application_id}`.

    Returns a small PII-safe payload so the applicant can see status +
    timeline + next-step guidance without authenticating.
    """
    # Basic ID-shape guard: all our ids are `app_{hex}` with 8-32 hex chars.
    if not application_id or not application_id.startswith("app_") or len(application_id) > 60:
        raise HTTPException(status_code=404, detail="Application not found")

    client_ip = request.client.host if request.client else "anon"
    _rate_limit_tracker(client_ip)

    doc = await db[APPS_COL].find_one(
        {"application_id": application_id},
        {
            "_id": 0,
            "application_id": 1,
            "role_title": 1,
            "role_slug": 1,
            "status": 1,
            "status_updated_at": 1,
            "created_at": 1,
            "name": 1,
            "attachment_count": 1,
            "rejected": 1,
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    status_raw = (doc.get("status") or "received").lower()
    rejected = bool(doc.get("rejected")) or status_raw in {"rejected", "declined"}

    # Build timeline: mark each step as done / active / pending based on the
    # stage we're at. A rejected application shows done up to the stage it
    # was rejected at, then a "Decision — not moving forward" node.
    stage_order = [t[0] for t in _STATUS_TIMELINE]
    try:
        current_idx = stage_order.index(status_raw)
    except ValueError:
        current_idx = 0  # default to first stage

    timeline: list[dict[str, Any]] = []
    for idx, (key, title, subtitle) in enumerate(_STATUS_TIMELINE):
        if rejected and idx > current_idx:
            # stop emitting future steps on rejected apps
            break
        if idx < current_idx:
            state = "done"
        elif idx == current_idx:
            state = "active"
        else:
            state = "pending"
        timeline.append({
            "key": key,
            "title": title,
            "subtitle": subtitle,
            "state": state,
        })

    if rejected:
        timeline.append({
            "key": "rejected",
            "title": "Decision",
            "subtitle": (
                "Unfortunately we're not moving forward at this time. "
                "We truly appreciate your interest and wish you the best."
            ),
            "state": "active",
        })

    # Scheduled interview lookup (cheap — at most 1 row per application)
    scheduled: dict[str, Any] | None = None
    try:
        iv = await db["careers_interviews"].find_one(
            {"application_id": application_id},
            {"_id": 0, "start_utc": 1, "interview_type": 1, "status": 1},
            sort=[("start_utc", 1)],
        )
        if iv and iv.get("status") in {"pending", "booked"}:
            scheduled = {
                "start_utc": iv.get("start_utc"),
                "interview_type": iv.get("interview_type") or "video",
            }
    except Exception as _e:  # pragma: no cover
        logger.debug(f"[careers/track] interview lookup skipped: {_e}")

    # Live queue context — total applicants for this role. Only published
    # when the count is ≥ 5, so small-role signals don't accidentally
    # identify the applicant's position. If the applicant is already past
    # the first gate (screening+), the "other applicants" count is hidden
    # because it no longer applies to their stage.
    role_queue: dict[str, Any] | None = None
    try:
        if doc.get("role_slug") and status_raw in {"received", "screening"}:
            total_in_role = await db[APPS_COL].count_documents({
                "role_slug": doc["role_slug"],
                "merged_into": {"$exists": False},
                "gdpr_soft_deleted_at": {"$exists": False},
            })
            if total_in_role >= 5:
                role_queue = {
                    "total_in_role": total_in_role,
                    "review_sla_hours": 48,
                }
    except Exception as _e:  # pragma: no cover
        logger.debug(f"[careers/track] queue lookup skipped: {_e}")

    first_name = (doc.get("name") or "").strip().split(" ", 1)[0] or "there"
    return {
        "application_id": doc["application_id"],
        "role_title": doc.get("role_title") or "Open Application",
        "role_slug": doc.get("role_slug"),
        "status": "rejected" if rejected else status_raw,
        "status_updated_at": doc.get("status_updated_at") or doc.get("created_at"),
        "submitted_at": doc.get("created_at"),
        "applicant_first_name": first_name,
        "attachment_count": int(doc.get("attachment_count") or 0),
        "timeline": timeline,
        "interview": scheduled,
        "role_queue": role_queue,
        "hiring_contact_email": "hiring@realaicoach.app",
    }


# ── Public: Applicant self-serve withdraw ───────────────────────────────
class WithdrawPayload(BaseModel):
    reason: str | None = None  # optional short free-text (max 500)


@router.post("/careers/applications/track/{application_id}/withdraw")
async def withdraw_application(
    application_id: str,
    payload: WithdrawPayload,
    request: Request,
):
    """Applicant-triggered self-withdraw. The `application_id` itself is the
    capability — the same unguessable token that powers the public tracker.

    Effects:
      • flips status to `withdrawn`, stamps `withdrawn_at` / `withdrawn_reason`
      • sends a Resend notice to the hiring inbox so recruiters see it live
      • returns the fresh tracker payload so the page can re-render without
        a second round-trip.

    Idempotent — a second call on an already-withdrawn app returns 200 with
    `already: true` instead of re-firing the notification email.
    """
    if not application_id or not application_id.startswith("app_") or len(application_id) > 60:
        raise HTTPException(status_code=404, detail="Application not found")

    client_ip = request.client.host if request.client else "anon"
    _rate_limit_tracker(client_ip)

    doc = await db[APPS_COL].find_one(
        {"application_id": application_id},
        {"_id": 0, "application_id": 1, "role_title": 1, "name": 1,
         "email": 1, "status": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    if doc.get("status") == "withdrawn":
        return {"ok": True, "already": True}

    reason = (payload.reason or "").strip()[:500]
    now = datetime.now(timezone.utc).isoformat()
    await db[APPS_COL].update_one(
        {"application_id": application_id},
        {"$set": {
            "status": "withdrawn",
            "status_updated_at": now,
            "status_updated_by": "applicant_self_service",
            "withdrawn_at": now,
            "withdrawn_reason": reason,
        }},
    )

    # Log a tracker event so the admin engagement strip picks it up.
    try:
        await db["careers_tracker_events"].insert_one({
            "application_id": application_id,
            "template": None,
            "event_type": "withdrawn",
            "received_at": now,
            "meta": {"reason": reason},
        })
    except Exception:  # pragma: no cover
        pass

    # Notify the recruiting inbox — fire-and-forget.
    try:
        import asyncio as _asyncio
        from utils.email_service import is_email_configured, send_catalog_template

        async def _notify():
            if not is_email_configured():
                return
            try:
                await send_catalog_template(
                    recipient_email="hiring@realaicoach.app",
                    template_key="career_applicant_withdraw_notice",
                    applicant_name=doc.get("name") or "(no name)",
                    applicant_email=doc.get("email") or "",
                    position=doc.get("role_title") or "(unknown role)",
                    application_id=application_id,
                    reason=reason or "(no reason provided)",
                    headers={"X-Application-ID": application_id},
                )
            except Exception as _e:  # pragma: no cover
                logger.warning(f"[careers/withdraw] notice email failed: {_e}")

        withdraw_notify_task = _asyncio.create_task(_notify())
        withdraw_notify_task.add_done_callback(
            lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
        )
    except Exception as _e:  # pragma: no cover
        logger.warning(f"[careers/withdraw] broadcast dispatch skipped: {_e}")

    return {"ok": True, "status": "withdrawn", "withdrawn_at": now}


# ── Admin: engagement strip (Resend open/click events) ─────────────────
@router.get("/admin/careers/applications/{application_id}/engagement")
async def application_engagement(application_id: str, request: Request):
    """Return a timeline of tracker-related events for a single application.

    Consumed by the in-panel "Engagement" strip in the admin applicant drawer.
    """
    from routes.careers_tier1 import require_admin  # local import avoids cycle
    await require_admin(request)

    cursor = db["careers_tracker_events"].find(
        {"application_id": application_id},
        {"_id": 0},
    ).sort("received_at", 1)

    events: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    last_ts: str | None = None
    async for ev in cursor:
        events.append(ev)
        counts[ev.get("event_type") or "unknown"] += 1
        last_ts = ev.get("received_at") or last_ts

    return {
        "application_id": application_id,
        "events": events,
        "counts": dict(counts),
        "last_event_at": last_ts,
        "total_events": len(events),
    }






# ── Public: AI-suggested cover-letter variants ───────────────────────────
class AISuggestPayload(BaseModel):
    name: str | None = None
    role_slug: str | None = None
    years_experience: str | None = None
    skills: list[str] | None = None
    strengths: str | None = None


class CareersTelemetryPayload(BaseModel):
    event: str = Field(min_length=2, max_length=120)
    source: str | None = Field(default=None, max_length=80)
    page: str | None = Field(default=None, max_length=120)
    ref: str | None = Field(default=None, max_length=120)
    job_slug: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] | None = None


async def _record_careers_public_event(
    request: Request,
    *,
    event: str,
    source: str = "",
    page: str = "",
    ref: str = "",
    job_slug: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    client_ip = request.client.host if request.client else "unknown"
    ua = (request.headers.get("user-agent") or "")[:280]
    referer = (request.headers.get("referer") or "")[:280]

    event_doc = {
        "event_id": f"car_evt_{uuid.uuid4().hex[:12]}",
        "event": event.strip().lower(),
        "source": source.strip(),
        "page": page.strip(),
        "ref": ref.strip(),
        "job_slug": job_slug.strip(),
        "metadata": metadata or {},
        "ip": client_ip,
        "user_agent": ua,
        "referer": referer,
        "created_at": now_iso,
    }
    await db["careers_public_events"].insert_one(event_doc)
    return {"ok": True, "event_id": event_doc["event_id"], "created_at": now_iso}


@router.get("/careers/telemetry")
async def careers_public_telemetry_get(
    request: Request,
    event: str,
    source: str = "",
    page: str = "",
    ref: str = "",
    job_slug: str = "",
):
    event_clean = str(event or "").strip()
    if len(event_clean) < 2:
        raise HTTPException(status_code=400, detail="event is required")
    return await _record_careers_public_event(
        request,
        event=event_clean,
        source=source,
        page=page,
        ref=ref,
        job_slug=job_slug,
        metadata={},
    )


@router.post("/careers/telemetry")
async def careers_public_telemetry(request: Request, payload: CareersTelemetryPayload):
    """Best-effort public telemetry for Careers conversion funnel."""
    return await _record_careers_public_event(
        request,
        event=payload.event,
        source=payload.source or "",
        page=payload.page or "",
        ref=payload.ref or "",
        job_slug=payload.job_slug or "",
        metadata=payload.metadata or {},
    )


@router.post("/careers/ai-suggest-cover-letter")
async def ai_suggest_cover_letter(payload: AISuggestPayload):
    """Returns 3 distinct cover-letter openers using Claude Sonnet 4.5 via Emergent LLM Key."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")

    role_title = "a role at RealAICoach"
    role_blurb = ""
    if payload.role_slug:
        job = await db[JOBS_COL].find_one({"slug": payload.role_slug}, {"_id": 0})
        if job:
            role_title = job.get("title", role_title)
            role_blurb = job.get("description", "")[:400]

    name_part = payload.name.strip() if payload.name else "the candidate"
    years = payload.years_experience or "some"
    skills = ", ".join(payload.skills or []) if payload.skills else "their diverse skill set"
    strengths = payload.strengths or ""

    prompt = f"""You are an elite career coach writing 3 cover-letter openers for an applicant.

Applicant: {name_part}
Role: {role_title}
Role blurb: {role_blurb}
Years of experience: {years}
Key skills: {skills}
Unique strengths / notes: {strengths}

Write 3 DISTINCT opening paragraphs (each 70-110 words) in 3 different tones:
  1. Confident & results-driven
  2. Warm & mission-aligned
  3. Bold & unconventional

Return STRICT JSON (no markdown):
{{"variants": [{{"tone": "Confident", "text": "..."}}, {{"tone": "Warm", "text": "..."}}, {{"tone": "Bold", "text": "..."}}]}}"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (
            LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"careers-{uuid.uuid4().hex[:8]}",
                    system_message="You write concise, authentic cover-letter openers. Return only the JSON specified.")
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
        )
        t0 = time.time()
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt)), timeout=25.0
        )
        latency_ms = int((time.time() - t0) * 1000)
        text = response.text if hasattr(response, "text") else str(response)
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        parsed = json.loads(clean.strip())
        try:
            from services.llm_usage_logger import log_llm_call
            await log_llm_call(model="claude-sonnet-4-5-20250929", provider="anthropic",
                               feature="careers-ai-cover", user_id=None, session_id="careers-public",
                               prompt_text=prompt, response_text=text, latency_ms=latency_ms, success=True)
        except Exception:
            pass
        variants = parsed.get("variants") or []
        if not variants:
            raise ValueError("No variants in response")
        return {"variants": variants[:3], "role_title": role_title}
    except Exception as e:
        logger.warning(f"[careers] ai suggest failed: {e}")
        return {
            "variants": [
                {"tone": "Confident", "text": f"Dear RealAICoach team,\n\nI am excited to apply for {role_title}. With {years} of focused experience and a deep grounding in {skills}, I have delivered outcomes that translate directly to the mission you describe. I am drawn to this opportunity because I believe my operational track record and bias toward shipping will compound the impact of the team. I look forward to exploring how I can contribute."},
                {"tone": "Warm", "text": f"Hello RealAICoach,\n\nYour mission resonates with why I chose this path. Over the last {years} years I have been building around {skills}, and your role for {role_title} is the most aligned opportunity I have come across this year. I would love to bring my curiosity and care to this team and help your customers achieve outcomes that matter."},
                {"tone": "Bold", "text": f"Hi there,\n\nI read the {role_title} description three times — each time I found a new angle where I think I can be uniquely useful. My background across {skills} gives me a perspective that blends execution speed with long-term systems thinking. If you are up for an unconventional hire who ships and iterates in public, I am confident you will not regret starting a conversation."},
            ],
            "role_title": role_title,
            "fallback": True,
        }


# ── Admin: CRUD ──────────────────────────────────────────────────────────
class JobCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=3, max_length=200)
    department: str
    location: str
    type: str
    level: str | None = None
    description: str = Field(min_length=10)
    requirements: list[str] = []
    salary_usd_min: int = 0
    salary_usd_max: int = 0
    hourly_rate_usd: int = 0
    status: str = "open"


class WeeklyCareersTemplateConfig(BaseModel):
    slug_base: str = Field(default="weekly-careers-opening", min_length=2, max_length=100)
    title: str = Field(default="Weekly Careers Opportunity", min_length=3, max_length=200)
    department: str = Field(default="General", min_length=2, max_length=120)
    location: str = Field(default="Remote", min_length=2, max_length=120)
    type: str = Field(default="Full-time", min_length=2, max_length=80)
    level: str | None = Field(default="Mid", max_length=80)
    description: str = Field(default="Join our growing team and apply through the Careers page.", min_length=10)
    requirements: list[str] = []
    salary_usd_min: int = 0
    salary_usd_max: int = 0
    hourly_rate_usd: int = 0


def _normalize_weekly_template_payload(payload: dict[str, Any]) -> dict[str, Any]:
    slug_base = str(payload.get("slug_base") or payload.get("title") or "weekly-careers-opening").strip().lower()
    slug_base = "-".join(part for part in "".join(ch if ch.isalnum() else "-" for ch in slug_base).split("-") if part) or "weekly-careers-opening"
    reqs_raw = payload.get("requirements") if isinstance(payload.get("requirements"), list) else []
    return {
        "slug_base": slug_base[:100],
        "title": str(payload.get("title") or "Weekly Careers Opportunity").strip()[:200],
        "department": str(payload.get("department") or "General").strip()[:120],
        "location": str(payload.get("location") or "Remote").strip()[:120],
        "type": str(payload.get("type") or "Full-time").strip()[:80],
        "level": (str(payload.get("level") or "").strip()[:80] or None),
        "description": str(payload.get("description") or "Join our growing team and apply through the Careers page.").strip(),
        "requirements": [str(item).strip() for item in reqs_raw if str(item).strip()][:12],
        "salary_usd_min": max(0, int(payload.get("salary_usd_min") or 0)),
        "salary_usd_max": max(0, int(payload.get("salary_usd_max") or 0)),
        "hourly_rate_usd": max(0, int(payload.get("hourly_rate_usd") or 0)),
    }


@router.get("/admin/careers/jobs")
async def admin_list_jobs(request: Request):
    await _require_admin(request)
    await _ensure_seeded()
    items: list[dict[str, Any]] = []
    async for d in db[JOBS_COL].find({}, {"_id": 0}).sort("posted_at", -1):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.post("/admin/careers/jobs")
async def admin_create_job(request: Request, body: JobCreate):
    user = await _require_admin(request)
    existing = await db[JOBS_COL].find_one({"slug": body.slug}, {"_id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="A job with that slug already exists")
    now = datetime.now(timezone.utc).isoformat()
    doc = body.model_dump()
    doc["job_id"] = f"job_{body.slug}"
    doc["posted_at"] = now
    doc["updated_at"] = now
    doc["created_by"] = getattr(user, "email", None)
    await db[JOBS_COL].insert_one(doc)
    return _clean(doc)


@router.put("/admin/careers/jobs/{slug}")
async def admin_update_job(request: Request, slug: str, body: dict[str, Any]):
    await _require_admin(request)
    body.pop("_id", None)
    body.pop("slug", None)
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db[JOBS_COL].update_one({"slug": slug}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Role not found")
    updated = await db[JOBS_COL].find_one({"slug": slug}, {"_id": 0})
    return updated or {}


@router.delete("/admin/careers/jobs/{slug}")
async def admin_delete_job(request: Request, slug: str):
    await _require_admin(request)
    res = await db[JOBS_COL].delete_one({"slug": slug})
    return {"deleted": res.deleted_count}


@router.post("/admin/careers/jobs/seed")
async def admin_reseed(request: Request):
    await _require_admin(request)
    await db[JOBS_COL].delete_many({})
    count = await _ensure_seeded()
    return {"seeded": count}


@router.get("/admin/careers/weekly-automation/template")
async def admin_get_weekly_careers_template(request: Request):
    await _require_admin(request)
    doc = await db.system_runtime_flags.find_one(
        {"key": WEEKLY_CAREERS_TEMPLATE_FLAG_KEY},
        {"_id": 0, "value": 1, "updated_at": 1, "updated_by": 1},
    ) or {}
    value = doc.get("value") if isinstance(doc.get("value"), dict) else {}
    return {
        "template": value,
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


@router.put("/admin/careers/weekly-automation/template")
async def admin_upsert_weekly_careers_template(request: Request, body: WeeklyCareersTemplateConfig):
    user = await _require_admin(request)
    now = datetime.now(timezone.utc).isoformat()
    normalized = _normalize_weekly_template_payload(body.model_dump())
    await db.system_runtime_flags.update_one(
        {"key": WEEKLY_CAREERS_TEMPLATE_FLAG_KEY},
        {
            "$set": {
                "key": WEEKLY_CAREERS_TEMPLATE_FLAG_KEY,
                "value": normalized,
                "updated_at": now,
                "updated_by": getattr(user, "email", "admin"),
            }
        },
        upsert=True,
    )
    return {
        "ok": True,
        "template": normalized,
        "updated_at": now,
        "updated_by": getattr(user, "email", "admin"),
    }


@router.post("/admin/careers/weekly-automation/run-now")
async def admin_run_weekly_careers_automation(request: Request, force: bool = False):
    user = await _require_admin(request)
    from scheduler_jobs import scheduled_weekly_careers_job_creation_and_announcement

    result = await scheduled_weekly_careers_job_creation_and_announcement(
        triggered_by=f"manual:{getattr(user, 'email', 'admin')}",
        force=bool(force),
    )
    return {"ok": True, "result": result}


@router.get("/admin/careers/applications")
async def admin_list_applications(request: Request, role_slug: str | None = None, limit: int = 200):
    await _require_admin(request)
    q: dict[str, Any] = {}
    if role_slug:
        q["role_slug"] = role_slug
    items: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 500)):
        items.append(d)
    return {"items": items, "count": len(items)}



# ──────────────────────────────────────────────────────────────────────────
# Admin bridging endpoints — shape adapters for CareerApplicationsPanel.tsx
# ──────────────────────────────────────────────────────────────────────────

def _adapt_application(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "application_id": row.get("application_id"),
        "full_name": row.get("name", ""),
        "email": row.get("email", ""),
        "phone": row.get("phone", ""),
        "position": row.get("role_title", "Open Application"),
        "department": row.get("department", ""),
        "cover_letter": row.get("cover_letter", ""),
        "linkedin_url": row.get("linkedin", ""),
        "portfolio_url": row.get("portfolio", ""),
        "experience_years": row.get("years_experience", ""),
        "status": row.get("status") or "received",
        "submitted_at": row.get("created_at", ""),
        "admin_notes": row.get("admin_notes", ""),
        "status_updated_at": row.get("status_updated_at", ""),
        "documents": row.get("documents", []),
        # Multi-attachment chips — written by /careers/apply via bind_attachments_to_application.
        "attachments": row.get("attachments", []),
        "attachment_count": int(row.get("attachment_count") or len(row.get("attachments") or [])),
        "interview": row.get("interview"),
        "recordings": row.get("recordings", []),
        "ai_analysis": row.get("ai_analysis"),
        # Applicant-reply thread (auto-threaded by /api/webhooks/inbound-email).
        # Recruiters use these two fields to drive the "Needs response"
        # filter and the unread badge on each row.
        "unread_applicant_replies": int(row.get("unread_applicant_replies") or 0),
        "last_applicant_reply_at": row.get("last_applicant_reply_at", ""),
    }


@router.get("/careers/applications")
async def admin_list_applications_bridge(request: Request):
    await _require_admin(request)
    jobs_by_slug: dict[str, str] = {}
    async for j in db[JOBS_COL].find({}, {"_id": 0, "slug": 1, "department": 1}):
        jobs_by_slug[j.get("slug", "")] = j.get("department", "")
    items: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(500):
        d["department"] = jobs_by_slug.get(d.get("role_slug") or "", d.get("department", ""))
        items.append(_adapt_application(d))
    return {"applications": items, "count": len(items)}


@router.get("/careers/applications/stats")
async def admin_applications_stats_bridge(request: Request):
    from datetime import timedelta
    await _require_admin(request)
    total = await db[APPS_COL].count_documents({})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_7d = await db[APPS_COL].count_documents({"created_at": {"$gte": cutoff}})
    by_status: dict[str, int] = {}
    async for d in db[APPS_COL].aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[d.get("_id") or "received"] = int(d.get("n") or 0)
    by_position: dict[str, int] = {}
    async for d in db[APPS_COL].aggregate([{"$group": {"_id": "$role_title", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}, {"$limit": 10}]):
        by_position[d.get("_id") or "Open Application"] = int(d.get("n") or 0)
    return {"total": total, "recent_7d": recent_7d, "by_status": by_status, "by_position": by_position}


@router.get("/careers/interviews/upcoming")
async def admin_upcoming_interviews(request: Request, days: int = 30):
    """Returns scheduled interviews with ISO date >= today for the next `days` days.

    Consumed by the ATS `UpcomingInterviewsWidget` calendar view.
    Shape per row:
      { application_id, full_name, email, position, date, time, type, notes,
        video_url, room_id, candidate_response, status }
    """
    await _require_admin(request)
    from datetime import timedelta
    days = max(1, min(int(days or 30), 180))
    today = datetime.now(timezone.utc).date().isoformat()
    horizon = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
    items: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find(
        {"interview.date": {"$gte": today, "$lte": horizon}},
        {"_id": 0},
    ).sort("interview.date", 1):
        iv = d.get("interview") or {}
        items.append({
            "application_id": d.get("application_id"),
            "full_name": d.get("name", "") or d.get("full_name", ""),
            "email": d.get("email", ""),
            "position": d.get("role_title", "Open Application"),
            "date": iv.get("date", ""),
            "time": iv.get("time", ""),
            "type": iv.get("type", "video"),
            "notes": iv.get("notes", ""),
            "video_url": iv.get("video_url", ""),
            "room_id": iv.get("room_id", ""),
            "candidate_response": iv.get("candidate_response", "pending"),
            "status": d.get("status") or "interview",
        })
    by_date: dict[str, int] = {}
    for row in items:
        by_date[row["date"]] = by_date.get(row["date"], 0) + 1
    return {
        "items": items,
        "count": len(items),
        "by_date": by_date,
        "range": {"start": today, "end": horizon, "days": days},
    }


class BulkICSBody(BaseModel):
    application_ids: list[str] | None = Field(
        default=None,
        description="Explicit app_ids. If omitted, sends to ALL candidates with interview.candidate_response=='accepted' scheduled in the next N days.",
    )
    days: int = 30
    only_accepted: bool = True


def _accepted_query(horizon_days: int, only_accepted: bool) -> dict[str, Any]:
    from datetime import timedelta
    today_iso = datetime.now(timezone.utc).date().isoformat()
    horizon_iso = (datetime.now(timezone.utc) + timedelta(days=max(1, min(int(horizon_days or 30), 180)))).date().isoformat()
    q: dict[str, Any] = {
        "interview.date": {"$gte": today_iso, "$lte": horizon_iso},
    }
    if only_accepted:
        q["interview.candidate_response"] = "accepted"
    return q


@router.get("/careers/applications/{app_id}/ics")
async def admin_download_interview_ics(request: Request, app_id: str):
    """Single-candidate ICS download (admin). Returns text/calendar body."""
    await _require_admin(request)
    from utils.ics_builder import build_interview_ics
    doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    iv = doc.get("interview") or {}
    ics = build_interview_ics(
        application_id=app_id,
        candidate_name=doc.get("name") or doc.get("full_name") or "Candidate",
        candidate_email=doc.get("email") or "",
        role_title=doc.get("role_title") or doc.get("position") or "Open Role",
        interview_date=iv.get("date") or "",
        interview_time=iv.get("time") or "",
        duration_minutes=int(iv.get("duration_minutes") or 45),
        interview_type=iv.get("type") or "video",
        video_url=iv.get("video_url") or "",
        notes=iv.get("notes") or "",
    )
    if not ics:
        raise HTTPException(status_code=400, detail="Interview slot is missing or malformed")
    filename = f"interview-{app_id}.ics"
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/careers/interviews/bulk-send-ics")
async def admin_bulk_send_ics(request: Request, body: BulkICSBody):
    """Send ICS calendar invites to selected candidates (default: every Accepted interview
    in the next N days). Each email includes the branded interview-invite template plus a
    `text/calendar` attachment that major mail clients render as an "Add to calendar" prompt.
    """
    await _require_admin(request)
    from utils.ics_builder import build_interview_ics, ics_attachment
    from utils.email_service import send_email
    from utils.email_templates import TEMPLATE_CATALOG

    if body.application_ids:
        rows_cur = db[APPS_COL].find({"application_id": {"$in": body.application_ids}}, {"_id": 0})
    else:
        rows_cur = db[APPS_COL].find(_accepted_query(body.days, body.only_accepted), {"_id": 0})

    results: list[dict[str, Any]] = []
    sent = 0
    skipped = 0
    builder_entry = TEMPLATE_CATALOG.get("career_interview_invite")
    builder = builder_entry.get("builder") if builder_entry else None

    async for doc in rows_cur:
        app_id = doc.get("application_id")
        email = (doc.get("email") or "").strip()
        iv = doc.get("interview") or {}
        status = doc.get("status") or ""
        if not app_id:
            continue
        if not email or "@" not in email:
            results.append({"application_id": app_id, "ok": False, "reason": "missing_email"})
            skipped += 1
            continue
        if not iv.get("date") or not iv.get("time"):
            results.append({"application_id": app_id, "ok": False, "reason": "missing_slot"})
            skipped += 1
            continue
        if status != "interview":
            # Do not spam people whose pipeline stage no longer matches.
            results.append({"application_id": app_id, "ok": False, "reason": "wrong_status"})
            skipped += 1
            continue

        candidate_name = doc.get("name") or doc.get("full_name") or "Candidate"
        role_title = doc.get("role_title") or doc.get("position") or "Open Role"
        ics = build_interview_ics(
            application_id=app_id,
            candidate_name=candidate_name,
            candidate_email=email,
            role_title=role_title,
            interview_date=iv.get("date"),
            interview_time=iv.get("time"),
            duration_minutes=int(iv.get("duration_minutes") or 45),
            interview_type=iv.get("type") or "video",
            video_url=iv.get("video_url") or "",
            notes=iv.get("notes") or "",
        )
        if not ics:
            results.append({"application_id": app_id, "ok": False, "reason": "ics_build_failed"})
            skipped += 1
            continue

        if not builder:
            results.append({"application_id": app_id, "ok": False, "reason": "template_unregistered"})
            skipped += 1
            continue

        tpl = builder(
            applicant_name=candidate_name,
            role_title=role_title,
            interview_date=iv.get("date"),
            interview_time=iv.get("time"),
            duration_minutes=int(iv.get("duration_minutes") or 45),
            interview_type=iv.get("type") or "video",
            timezone_label="UTC",
            confirm_url=iv.get("confirm_url") or "",
            message=iv.get("notes") or "",
        )
        try:
            send_res = await send_email(
                recipient_email=email,
                recipient_name=candidate_name,
                subject=tpl.subject,
                content=tpl.html,
                content_text=tpl.text,
                template_key="career_interview_invite",
                attachments=[ics_attachment(ics, filename=f"interview-{app_id}.ics")],
            )
            ok = bool(send_res and send_res.get("success") is not False)
        except Exception as e:
            logger.warning(f"[careers] bulk-ics send failed for {app_id}: {e}")
            ok = False

        if ok:
            await db[APPS_COL].update_one(
                {"application_id": app_id},
                {"$set": {
                    "interview.ics_last_sent_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            sent += 1
            results.append({"application_id": app_id, "ok": True, "email": email})
        else:
            skipped += 1
            results.append({"application_id": app_id, "ok": False, "reason": "send_failed", "email": email})

    return {
        "ok": True,
        "sent": sent,
        "skipped": skipped,
        "total_attempted": sent + skipped,
        "results": results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


class StatusUpdate(BaseModel):
    status: str
    admin_notes: str | None = None
    send_email: bool = False
    interview_date: str | None = None
    interview_time: str | None = None
    interview_type: str | None = None
    interview_notes: str | None = None


@router.patch("/careers/applications/{app_id}/status")
async def admin_update_application_status(request: Request, app_id: str, body: StatusUpdate):
    await _require_admin(request)
    valid = {"received", "under_review", "interview", "offer", "rejected"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(valid)}")
    now = datetime.now(timezone.utc).isoformat()
    update: dict[str, Any] = {"status": body.status, "status_updated_at": now}
    if body.admin_notes is not None:
        update["admin_notes"] = body.admin_notes
    if body.interview_date or body.interview_time:
        update["interview"] = {
            "date": body.interview_date or "", "time": body.interview_time or "",
            "type": body.interview_type or "video", "notes": body.interview_notes or "",
            "room_id": f"iv_{app_id}", "video_url": "",
        }
    res = await db[APPS_COL].update_one({"application_id": app_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    if body.send_email:
        try:
            from utils.email_service import send_email
            from utils.email_templates import TEMPLATE_CATALOG
            doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
            if doc and doc.get("email"):
                status_to_key = {
                    "received": "career_status_received",
                    "under_review": "career_status_under_review",
                    "interview": "career_status_interview",
                    "offer": "career_status_offer",
                    "rejected": "career_status_rejected",
                }
                tpl_key = status_to_key.get(body.status, "career_status_update")
                builder_entry = TEMPLATE_CATALOG.get(tpl_key)
                if builder_entry and builder_entry.get("builder"):
                    # Auto-attach live portal link to every status email footer
                    portal_url = ""
                    portal_token = doc.get("portal_token")
                    if not portal_token:
                        portal_token = secrets.token_urlsafe(24) if False else __import__("secrets").token_urlsafe(24)
                        await db[APPS_COL].update_one(
                            {"application_id": app_id},
                            {"$set": {"portal_token": portal_token, "portal_token_issued_at": datetime.now(timezone.utc).isoformat()}},
                        )
                    try:
                        fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
                        fwd_scheme = request.headers.get("x-forwarded-proto") or "https"
                        portal_url = f"{fwd_scheme}://{fwd_host}/careers/portal/{portal_token}"
                    except Exception:
                        portal_url = f"https://realaicoach.app/careers/portal/{portal_token}"
                    notes_with_portal = (body.admin_notes or "")
                    if notes_with_portal:
                        notes_with_portal = notes_with_portal + "\n\n"
                    notes_with_portal += f"Track your application live: {portal_url}"
                    tpl = builder_entry["builder"](
                        applicant_name=doc.get("name") or doc.get("full_name") or "there",
                        role_title=doc.get("role_title") or doc.get("position") or "the role",
                        application_id=app_id,
                        notes=notes_with_portal,
                    )
                    await send_email(
                        recipient_email=doc["email"],
                        recipient_name=doc.get("name"),
                        subject=tpl.subject,
                        content=tpl.html,
                        content_text=tpl.text,
                        template_key=tpl_key,
                    )
                else:
                    logger.warning(f"[careers] template_key {tpl_key} not registered — skipped email")
        except Exception as _e:
            logger.debug(f"[careers] status email skipped: {_e}")
    # Auto-tag silver medalists on rejection (T3 feature #4)
    if body.status == "rejected":
        try:
            from routes.careers_tier3 import auto_tag_silver_medalist
            import asyncio as _asyncio
            silver_medalist_task = _asyncio.create_task(auto_tag_silver_medalist(app_id))
            silver_medalist_task.add_done_callback(
                lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
            )
        except Exception as _e:
            logger.debug(f"[careers] silver-medalist auto-tag dispatch skipped: {_e}")
    return {"success": True, "application_id": app_id, "status": body.status}



class AISuggestNoteBody(BaseModel):
    status: str = Field(..., description="Target status: received|under_review|interview|offer|rejected")
    tone: str | None = "professional"  # professional | warm | direct
    seed: str | None = None  # optional short seed / context from the recruiter


@router.post("/careers/applications/{app_id}/ai-suggest-note")
async def admin_ai_suggest_note(request: Request, app_id: str, body: AISuggestNoteBody):
    """Generate an admin note draft (concise, status-aware) using Claude Sonnet 4.5.
    Used as a one-click suggestion inside the Update Status panel in the admin ATS UI."""
    await _require_admin(request)
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")

    valid = {"received", "under_review", "interview", "offer", "rejected"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(valid)}")

    doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    candidate_name = doc.get("name") or doc.get("full_name") or "the candidate"
    role_title = doc.get("role_title") or doc.get("position") or "the role"
    years_exp = doc.get("years_experience") or doc.get("experience_years") or ""
    skills = ", ".join(doc.get("skills") or [])[:200]
    cover = (doc.get("cover_letter") or "")[:800]
    prev_notes = (doc.get("admin_notes") or "")[:400]

    status_label = {
        "received": "Received (first acknowledgement)",
        "under_review": "Under Review (hiring panel is actively reviewing)",
        "interview": "Interview (advancing to interview stage)",
        "offer": "Offer (extending an offer)",
        "rejected": "Rejected (respectful decline)",
    }[body.status]

    tone = (body.tone or "professional").lower()
    tone_hint = {
        "professional": "Professional, crisp, respectful.",
        "warm": "Warm, genuinely human, encouraging.",
        "direct": "Direct and concise — no fluff.",
    }.get(tone, "Professional, crisp, respectful.")

    prompt = f"""You are writing an INTERNAL admin note for a hiring console — the recruiter will see this when updating a candidate's status to "{status_label}".

Candidate: {candidate_name}
Role: {role_title}
Years of experience: {years_exp}
Key skills: {skills}
Cover letter excerpt: {cover}
Previous internal notes: {prev_notes}
Seed/context from recruiter: {body.seed or 'none'}
Tone: {tone_hint}

Write ONE admin note (45–90 words). Rules:
- Internal-only (recruiter reads, candidate does NOT see this verbatim).
- Be specific to the candidate's profile; no generic filler.
- Include a concrete next action or observation relevant to "{status_label}".
- No emojis. No markdown. Plain prose only.
- If status is "rejected", keep it factual and respectful — note the specific reason(s).
- If status is "offer", include a one-line rationale (why they stood out).

Return STRICT JSON: {{"note": "..."}}"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (
            LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"careers-note-{app_id[-6:]}-{uuid.uuid4().hex[:6]}",
                    system_message="You write concise, specific internal admin notes. Return only the JSON specified.")
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
        )
        t0 = time.time()
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt)), timeout=25.0
        )
        latency_ms = int((time.time() - t0) * 1000)
        text = response.text if hasattr(response, "text") else str(response)
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        parsed = json.loads(clean.strip())
        note = (parsed.get("note") or "").strip()
        if not note:
            raise ValueError("Empty note in AI response")
        try:
            from services.llm_usage_logger import log_llm_call
            await log_llm_call(model="claude-sonnet-4-5-20250929", provider="anthropic",
                               feature="careers-ai-admin-note", user_id=None, session_id=f"careers-note-{app_id[-6:]}",
                               prompt_text=prompt, response_text=text, latency_ms=latency_ms, success=True)
        except Exception:
            pass
        return {"success": True, "note": note, "status": body.status, "tone": tone}
    except Exception as e:
        logger.warning(f"[careers] ai-suggest-note failed for {app_id}: {e}")
        raise HTTPException(status_code=502, detail="AI suggestion failed — please try again")



class InterviewInviteBody(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    time: str = Field(..., description="HH:MM (24h, local to candidate)")
    duration_minutes: int = 45
    interview_type: str = "video"  # video|phone|onsite
    message: str | None = None
    cc: list[str] | None = None
    timezone: str | None = "UTC"


def _build_ics(*, uid: str, summary: str, description: str,
               start_iso: str, end_iso: str, location: str, organizer_email: str,
               attendee_email: str) -> bytes:
    """Minimal RFC 5545 ICS file (VEVENT)."""
    def _fmt(dt_iso: str) -> str:
        # Expect 'YYYY-MM-DDTHH:MM:SS' (naive UTC here)
        return dt_iso.replace("-", "").replace(":", "").replace("T", "T").split(".")[0] + "Z"

    def esc(value: str) -> str:
        return (value or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//RealAICoach//Careers Interview//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt(datetime.now(timezone.utc).isoformat())}",
        f"DTSTART:{_fmt(start_iso)}",
        f"DTEND:{_fmt(end_iso)}",
        f"SUMMARY:{esc(summary)}",
        f"DESCRIPTION:{esc(description)}",
        f"LOCATION:{esc(location)}",
        f"ORGANIZER;CN=RealAICoach Talent:mailto:{organizer_email}",
        f"ATTENDEE;CN={attendee_email};RSVP=TRUE;ROLE=REQ-PARTICIPANT:mailto:{attendee_email}",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "BEGIN:VALARM",
        "TRIGGER:-PT30M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{esc(summary)} starts in 30 minutes",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


@router.post("/careers/applications/{app_id}/invite-interview")
async def admin_invite_interview(request: Request, app_id: str, body: InterviewInviteBody):
    """One-click interview invite: persists slot + moves status to 'interview' + sends
    a Resend email with ICS calendar attachment + returns the in-app video_url."""
    admin_user = await _require_admin(request)
    doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if not doc.get("email"):
        raise HTTPException(status_code=400, detail="Application has no email on file")

    # Basic payload validation
    try:
        start_dt = datetime.strptime(f"{body.date} {body.time}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time. Expected YYYY-MM-DD HH:MM")
    duration = max(15, min(body.duration_minutes or 45, 240))
    from datetime import timedelta
    end_dt = start_dt + timedelta(minutes=duration)

    room_id = f"iv_{app_id[-8:]}_{int(start_dt.timestamp())}"
    candidate_token = secrets.token_urlsafe(32)
    # Reuse in-app video pattern: /video/join?room_id=<id>&name=<candidate>
    video_path = f"/video/join?room_id={room_id}&name={(doc.get('name') or 'Candidate').replace(' ', '+')}&appId={app_id}"
    # Use request's scheme + host to build absolute URL for email
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    video_url = f"{scheme}://{host}{video_path}"
    public_confirm_url = f"{scheme}://{host}/careers/interview/confirm?token={candidate_token}"
    location_label = {"video": video_url, "phone": "Phone interview", "onsite": "On-site (details to follow)"}.get(body.interview_type, video_url)

    interview_block = {
        "date": body.date,
        "time": body.time,
        "type": body.interview_type,
        "duration_minutes": duration,
        "timezone": body.timezone or "UTC",
        "notes": body.message or "",
        "room_id": room_id,
        "video_url": video_url,
        "invited_at": datetime.now(timezone.utc).isoformat(),
        "invited_by": getattr(admin_user, "email", None) or getattr(admin_user, "user_id", None),
        "candidate_token": candidate_token,
        "candidate_response": "pending",
        "public_confirm_url": public_confirm_url,
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    await db[APPS_COL].update_one(
        {"application_id": app_id},
        {"$set": {"interview": interview_block, "status": "interview", "status_updated_at": now_iso}},
    )

    # Build email HTML
    candidate_name = doc.get("name") or doc.get("full_name") or "there"
    role_title = doc.get("role_title") or doc.get("position") or "your role"
    start_dt.strftime("%A, %B %-d, %Y · %H:%M UTC")

    # Build ICS attachment
    ics_bytes = _build_ics(
        uid=f"{room_id}@realaicoach.app",
        summary=f"Interview: {role_title} at RealAICoach",
        description=(body.message or "We look forward to speaking with you.") + (f"\n\nJoin: {video_url}" if body.interview_type == "video" else ""),
        start_iso=start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        end_iso=end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        location=location_label,
        organizer_email="talent@realaicoach.app",
        attendee_email=doc["email"],
    )
    import base64
    ics_b64 = base64.b64encode(ics_bytes).decode("ascii")

    sent_ok = False
    sent_error: str | None = None
    try:
        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        # Build via the registered V7 template so no raw-HTML auto-wrap warning fires
        tpl = TEMPLATE_CATALOG["career_interview_invite"]["builder"](
            applicant_name=candidate_name,
            role_title=role_title,
            interview_date=body.date,
            interview_time=body.time,
            duration_minutes=duration,
            interview_type=body.interview_type,
            timezone_label=body.timezone or "UTC",
            confirm_url=public_confirm_url,
            message=body.message or "",
        )
        result = await send_email(
            recipient_email=doc["email"],
            recipient_name=candidate_name,
            subject=tpl.subject,
            content=tpl.html,
            content_text=tpl.text,
            template_key="career_interview_invite",
            attachments=[{
                "filename": "interview.ics",
                "content": ics_b64,
                "content_type": "text/calendar; method=REQUEST; charset=UTF-8",
            }],
        )
        sent_ok = bool(result and result.get("success"))
        if not sent_ok:
            sent_error = (result or {}).get("error") or "email send returned non-success"
    except Exception as e:
        sent_error = str(e)[:160]
        logger.warning(f"[careers] invite-interview email failed for {app_id}: {e}")

    return {
        "success": True,
        "application_id": app_id,
        "status": "interview",
        "interview": interview_block,
        "email_sent": sent_ok,
        "email_error": sent_error,
        "video_url": video_url,
    }



# ── Public candidate handshake endpoints (token-authenticated) ──────────
async def _find_by_candidate_token(token: str) -> dict[str, Any]:
    if not token or len(token) < 16:
        raise HTTPException(status_code=400, detail="Invalid token")
    doc = await db[APPS_COL].find_one({"interview.candidate_token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Interview link is invalid or has expired")
    return doc


def _public_interview_view(doc: dict[str, Any]) -> dict[str, Any]:
    iv = doc.get("interview") or {}
    return {
        "application_id": doc.get("application_id"),
        "candidate_name": doc.get("name") or doc.get("full_name") or "",
        "candidate_email": doc.get("email", ""),
        "role_title": doc.get("role_title") or doc.get("position") or "",
        "interview": {
            "date": iv.get("date"),
            "time": iv.get("time"),
            "duration_minutes": iv.get("duration_minutes", 45),
            "type": iv.get("type", "video"),
            "timezone": iv.get("timezone", "UTC"),
            "notes": iv.get("notes", ""),
            "video_url": iv.get("video_url"),
            "candidate_response": iv.get("candidate_response", "pending"),
            "responded_at": iv.get("responded_at"),
            "reschedule_reason": iv.get("reschedule_reason"),
            "proposed_slots": iv.get("proposed_slots", []),
        },
    }


@router.get("/careers/interview/public/{token}")
async def public_get_interview(token: str):
    doc = await _find_by_candidate_token(token)
    return {"success": True, **_public_interview_view(doc)}


async def _notify_recruiter(event_type: str, severity: str, title: str, summary: str, fields: dict[str, Any], url: str | None):
    """Fire-and-forget Slack/Teams alert, bypassing enabled_events filter."""
    try:
        from services.webhook_alerts import get_config, _build_slack_payload, _build_teams_payload, _post_webhook
        cfg = await get_config()
        slack_url = cfg.get("slack_webhook_url") or ""
        teams_url = cfg.get("teams_webhook_url") or ""
        if slack_url:
            asyncio.ensure_future(_post_webhook(slack_url,
                _build_slack_payload(event_type, severity, title, summary, fields, url)))
        if teams_url:
            asyncio.ensure_future(_post_webhook(teams_url,
                _build_teams_payload(event_type, severity, title, summary, fields, url)))
        # Audit log
        try:
            await db.webhook_alerts_log.insert_one({
                "created_at": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type, "severity": severity,
                "title": title, "summary": summary, "fields": fields, "url": url,
                "dispatched": bool(slack_url or teams_url),
            })
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[careers] recruiter notify failed: {e}")


@router.post("/careers/interview/public/{token}/accept")
async def public_accept_interview(token: str, request: Request):
    doc = await _find_by_candidate_token(token)
    app_id = doc["application_id"]
    now_iso = datetime.now(timezone.utc).isoformat()
    await db[APPS_COL].update_one(
        {"application_id": app_id},
        {"$set": {"interview.candidate_response": "accepted", "interview.responded_at": now_iso}},
    )
    iv = doc.get("interview") or {}
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    admin_deep_link = f"{scheme}://{host}/admin-console?category=people&tab=career-applications"
    await _notify_recruiter(
        event_type="career_interview_confirmed",
        severity="info",
        title="✅ Interview confirmed by candidate",
        summary=f"{doc.get('name','Candidate')} accepted the {iv.get('type','video')} interview for {doc.get('role_title','')}.",
        fields={
            "Candidate": f"{doc.get('name','')} <{doc.get('email','')}>",
            "Role": doc.get("role_title", ""),
            "When": f"{iv.get('date','')} {iv.get('time','')} UTC · {iv.get('duration_minutes',45)} min",
            "Type": iv.get("type", "video"),
        },
        url=admin_deep_link,
    )
    # Fresh doc to reflect candidate_response
    fresh = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    return {"success": True, **_public_interview_view(fresh or doc)}


class PublicProposedSlot(BaseModel):
    date: str
    time: str


class PublicRescheduleBody(BaseModel):
    reason: str | None = None
    proposed_slots: list[PublicProposedSlot] = Field(default_factory=list)


@router.post("/careers/interview/public/{token}/reschedule")
async def public_reschedule_interview(token: str, body: PublicRescheduleBody, request: Request):
    doc = await _find_by_candidate_token(token)
    if not (body.reason or body.proposed_slots):
        raise HTTPException(status_code=400, detail="Please include a reason or at least one proposed slot")
    if len(body.proposed_slots) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 proposed slots")

    app_id = doc["application_id"]
    now_iso = datetime.now(timezone.utc).isoformat()
    slots_list = [{"date": s.date, "time": s.time} for s in body.proposed_slots]
    await db[APPS_COL].update_one(
        {"application_id": app_id},
        {"$set": {
            "interview.candidate_response": "reschedule_requested",
            "interview.responded_at": now_iso,
            "interview.reschedule_reason": body.reason or "",
            "interview.proposed_slots": slots_list,
        }},
    )
    iv = doc.get("interview") or {}
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    admin_deep_link = f"{scheme}://{host}/admin-console?category=people&tab=career-applications"
    slots_txt = ", ".join([f"{s['date']} {s['time']}" for s in slots_list]) or "—"
    await _notify_recruiter(
        event_type="career_interview_reschedule_requested",
        severity="warning",
        title="🔁 Candidate requested a reschedule",
        summary=f"{doc.get('name','Candidate')} asked to reschedule the interview for {doc.get('role_title','')}.",
        fields={
            "Candidate": f"{doc.get('name','')} <{doc.get('email','')}>",
            "Role": doc.get("role_title", ""),
            "Original slot": f"{iv.get('date','')} {iv.get('time','')} UTC",
            "Proposed slots": slots_txt,
            "Reason": body.reason or "—",
        },
        url=admin_deep_link,
    )
    fresh = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    return {"success": True, **_public_interview_view(fresh or doc)}





@router.post("/careers/interview/analyze/{app_id}")
async def admin_analyze_interview(request: Request, app_id: str):
    """AI scoring of an application using Claude Sonnet 4.5."""
    await _require_admin(request)
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")
    doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")

    prompt = f"""You are a senior hiring manager. Score this application on 1-10 scale per dimension.

Role: {doc.get('role_title', 'Unknown')}
Candidate: {doc.get('name', '')}
Years experience: {doc.get('years_experience', '—')}
Skills: {', '.join(doc.get('skills') or [])}
LinkedIn: {doc.get('linkedin', '—')}
Cover letter:
{doc.get('cover_letter', '')}

Return STRICT JSON:
{{"summary": "...", "key_points": ["..."], "strengths": ["..."], "weaknesses": ["..."],
  "communication_score": 0-10, "technical_score": 0-10, "cultural_fit_score": 0-10, "overall_score": 0-10,
  "recommendation": "strong_hire|hire|maybe|no_hire", "recommendation_reason": "..."}}"""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"iv-{app_id}",
                         system_message="Return only the JSON specified.")
                .with_model("anthropic", "claude-sonnet-4-5-20250929"))
        t0 = time.time()
        res = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=30.0)
        latency_ms = int((time.time() - t0) * 1000)
        text = (res.text if hasattr(res, "text") else str(res)).strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        analysis = json.loads(text.strip())
        ai_block = {
            "transcript": doc.get("cover_letter", "")[:2000],
            "analysis": analysis,
            "recording_id": "",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[APPS_COL].update_one({"application_id": app_id}, {"$set": {"ai_analysis": ai_block}})
        try:
            from services.llm_usage_logger import log_llm_call
            await log_llm_call(model="claude-sonnet-4-5-20250929", provider="anthropic",
                               feature="careers-interview-analyze", user_id=None, session_id=f"iv-{app_id}",
                               prompt_text=prompt, response_text=text, latency_ms=latency_ms, success=True)
        except Exception:
            pass
        return {"success": True, "ai_analysis": ai_block}
    except Exception as e:
        logger.warning(f"[careers] AI interview analyze failed for {app_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)[:120]}")


def _build_candidate_comparison_pdf(rows: list[dict[str, Any]]) -> tuple[bytes, str]:
    """Build candidate comparison PDF bytes + canonical filename."""
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from services.pdf_v15_theme import PALETTE, draw_page_chrome

    generated_at = datetime.now(timezone.utc)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=1.55 * inch, bottomMargin=0.9 * inch, title="Candidate Comparison")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=PALETTE["primary"], fontSize=18, spaceAfter=12)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=PALETTE["ink"], fontSize=13, spaceAfter=6)
    body_s = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14)
    meta_s = ParagraphStyle("meta", parent=styles["BodyText"], fontSize=9, textColor=PALETTE["slate"], leading=12)

    story = [Paragraph("Candidate Comparison", h1),
             Paragraph(f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')} · {len(rows)} candidate(s)", meta_s),
             Spacer(1, 12)]

    for i, r in enumerate(rows):
        story.append(Paragraph(f"{r.get('name') or r.get('full_name') or '(no name)'} — {r.get('role_title') or r.get('position') or ''}", h2))
        meta_bits = [
            f"Email: {r.get('email','')}",
            f"Phone: {r.get('phone','—')}",
            f"Experience: {r.get('years_experience') or r.get('experience_years') or '—'}",
            f"Status: {r.get('status','submitted')}",
            f"Submitted: {r.get('submitted_at','')[:10]}",
        ]
        story.append(Paragraph(" · ".join(meta_bits), meta_s))
        story.append(Spacer(1, 6))
        if r.get("linkedin") or r.get("linkedin_url"):
            story.append(Paragraph(f"LinkedIn: {r.get('linkedin') or r.get('linkedin_url')}", body_s))
        skills = r.get("skills") or []
        if skills:
            story.append(Paragraph(f"<b>Skills:</b> {', '.join(skills)}", body_s))
        cl = (r.get("cover_letter") or "").strip()
        if cl:
            story.append(Paragraph("<b>Cover letter:</b>", body_s))
            story.append(Paragraph(cl.replace("\n", "<br/>")[:4000], body_s))
        ai = r.get("ai_analysis") or {}
        analysis = ai.get("analysis") if isinstance(ai, dict) else None
        if analysis:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"<b>AI Analysis:</b> Overall {analysis.get('overall_score','—')}/10 · "
                f"Rec: {analysis.get('recommendation','—')}", body_s))
            if analysis.get("summary"):
                story.append(Paragraph(str(analysis["summary"])[:800], body_s))
        if i < len(rows) - 1:
            story.append(PageBreak())

    def _draw_chrome(canv, build_doc):
        draw_page_chrome(
            canv,
            width=float(build_doc.pagesize[0]),
            height=float(build_doc.pagesize[1]),
            margin_x=0.6 * inch,
            page_no=canv.getPageNumber(),
            title="Candidate Comparison",
            subtitle="Jobs Portal • enterprise shortlist review",
            right_primary=f"Candidates: {len(rows)}",
            right_secondary=generated_at.strftime("%Y-%m-%d %H:%M UTC"),
            badge_text="CANDIDATE SHORTLIST EVALUATION",
            badge_status="INFO",
            footer_text="RealAICoach Jobs Portal • Enterprise profile",
        )

    doc.build(story, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)
    pdf_bytes = buf.getvalue()
    buf.close()
    filename = build_pdf_v15_filename("candidate-comparison", generated_at.strftime('%Y%m%d'))
    return pdf_bytes, filename


@router.post("/careers/comparison/export-pdf")
async def admin_export_comparison_pdf(request: Request, body: dict[str, Any]):
    """Generate a PDF snapshot of the candidate comparison view."""
    await _require_admin(request)
    ids = body.get("application_ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="application_ids required")
    rows: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find({"application_id": {"$in": ids}}, {"_id": 0}):
        rows.append(d)

    pdf_bytes, filename = _build_candidate_comparison_pdf(rows)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ShareEmailBody(BaseModel):
    application_ids: list[str]
    # Accept both legacy single-recipient and modern multi-recipient shapes
    to_email: str | None = None
    recipients: list[str] | None = None
    note: str | None = None
    message: str | None = None


@router.post("/careers/comparison/share-email")
async def admin_share_comparison_email(request: Request, body: ShareEmailBody):
    await _require_admin(request)
    if not body.application_ids:
        raise HTTPException(status_code=400, detail="application_ids required")

    # Normalize recipients list (supports to_email legacy + recipients[] modern)
    recipients: list[str] = []
    if body.recipients:
        recipients.extend([r.strip() for r in body.recipients if r and "@" in r])
    if body.to_email and "@" in body.to_email:
        recipients.append(body.to_email.strip())
    # dedupe, preserve order
    seen: set[str] = set()
    recipients = [r for r in recipients if not (r in seen or seen.add(r))]
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient email required")

    rows: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find({"application_id": {"$in": body.application_ids}}, {"_id": 0}):
        rows.append(d)
    items_html = "".join([
        f"<li><strong>{r.get('name') or r.get('full_name','')}</strong> — {r.get('role_title') or r.get('position','')} · <a href='mailto:{r.get('email','')}'>{r.get('email','')}</a></li>"
        for r in rows
    ])
    import base64
    pdf_bytes, pdf_filename = _build_candidate_comparison_pdf(rows)
    comparison_attachment = {
        "filename": pdf_filename,
        "content": base64.b64encode(pdf_bytes).decode("utf-8"),
        "content_type": "application/pdf",
    }
    note = body.message or body.note or "Sharing shortlisted candidates for your review."
    # Wrap in V7 shell so the outbound HTML carries the `em-outer` fingerprint
    # and passes the hard-block raw-HTML guardrail in utils/email_service.py.
    from utils.email_templates import _wrap, _lead, _callout, DASH_URL
    inner = _lead("Candidate Shortlist", note) + f'<ul class="em-list" style="margin:0 0 16px 20px;padding:0;">{items_html}</ul>' + _callout("The full PDF comparison report with scores, strengths, and AI recommendations is available in the Careers admin console.")
    html = _wrap(
        "Candidate Shortlist",
        f"{len(rows)} candidates shared for your review",
        inner,
        "Open Careers Console",
        f"{DASH_URL}/admin-console?tab=career-applications",
        category="careers",
    )

    sent: list[str] = []
    failed: list[str] = []
    try:
        from utils.email_service import send_email
        for to in recipients:
            try:
                await send_email(recipient_email=to, subject=f"Candidate shortlist ({len(rows)} candidates)",
                                 content=html, template_key="career_shortlist_share", attachments=[comparison_attachment])
                sent.append(to)
            except Exception as inner_e:
                logger.warning(f"[careers] share-email failed for {to}: {inner_e}")
                failed.append(to)
    except Exception as e:
        logger.warning(f"[careers] share-email dispatch failed: {e}")
        raise HTTPException(status_code=502, detail="Email send failed")

    return {
        "success": len(sent) > 0,
        "sent": sent,
        "failed": failed,
        "recipients": len(sent),
        "candidates": len(rows),
        "message": f"Sent to {len(sent)} recipient(s)" if sent else "Failed to send to any recipient",
    }
