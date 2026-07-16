"""Public social-proof endpoints for the Welcome page.

No auth. No PII. Powers the live tickertape:
  GET  /api/public/signups-recent           — recent-signup micro-badge (cached 15s)
  GET  /api/public/coaching-tip-of-the-day  — daily curated coaching tip (DB-backed)
  POST /api/public/tickertape-event         — CTR telemetry (impressions + clicks)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Curated seed for the public coaching-tip catalog ─────────────────────
# First-run seed for the `public_coaching_tips` collection. After seed,
# admins manage tips via /api/admin/coaching-tips. Kept here so fresh
# deploys always have a non-empty tickertape on Welcome.
PUBLIC_COACHING_TIPS: list[dict[str, str]] = [
    {"title": "Small reps compound", "content": "15 focused minutes daily beats 3 scattered hours weekly."},
    {"title": "Specific > generic", "content": "Replace 'get better at leadership' with 'give one direct-report feedback this week'."},
    {"title": "Energy audits beat time audits", "content": "Track what drains you for a week. Protect the 2 hours you're sharpest."},
    {"title": "Teach to retain", "content": "Explain a new skill to a peer within 48 hours — retention jumps ~2x."},
    {"title": "Debrief the wins too", "content": "Reviewing what worked builds a playbook. Failure-only reviews build scars."},
    {"title": "Prime the calendar", "content": "Book deep-work blocks before anyone else can book you. Calendars are first-come."},
    {"title": "Raise the floor, not the ceiling", "content": "Your worst week matters more than your best. Shore up the floor."},
    {"title": "Ask for the decision", "content": "In 1:1s, end with 'What's the one decision you need from me today?' It 3x's momentum."},
    {"title": "Name the tradeoff", "content": "Every 'yes' is a 'no' to something else. Naming it out loud clarifies priority."},
    {"title": "Feedback in 48h", "content": "Delayed feedback gets rationalized away. Say it within two days or don't say it."},
]


TIPS_COL = "public_coaching_tips"
TICKERTAPE_COL = "tickertape_events"

# ── In-process TTL cache for /signups-recent ─────────────────────────────
# count_documents() is cheap but not free at scale. Cache the result per
# `minutes` window for 15s so a burst of Welcome-page visitors collapses
# into a single DB read. Paired with Cache-Control: public, max-age=15
# so CDNs/browsers also dedupe.
_SIGNUPS_CACHE_TTL_S = 15
_signups_cache: dict[int, tuple[float, dict[str, Any]]] = {}


async def _ensure_tips_seeded() -> None:
    """If `public_coaching_tips` is empty, insert the curated seed list so
    fresh deploys always have content for the tickertape. Subsequent
    calls skip the count_documents(). Idempotent."""
    try:
        n = await db[TIPS_COL].count_documents({})
        if n > 0:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        docs = []
        for i, t in enumerate(PUBLIC_COACHING_TIPS):
            docs.append({
                "tip_id": f"seed-{i:03d}",
                "title": t["title"],
                "content": t["content"],
                "is_active": True,
                "position": i,
                "created_at": now_iso,
                "updated_at": now_iso,
                "created_by": "system-seed",
            })
        if docs:
            await db[TIPS_COL].insert_many(docs)
            logger.info(f"[public_social_proof] Seeded {len(docs)} public coaching tips.")
    except Exception as e:
        logger.warning(f"[public_social_proof] tip seed failed: {e}")


# ─────────────────────────────────────────────────────────────────────────
# Public endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get("/public/signups-recent")
async def public_signups_recent(
    response: Response,
    minutes: int = Query(60, ge=5, le=1440, description="Look-back window in minutes."),
):
    """Return raw signup count in the last N minutes. Cached 15s in-process
    AND advertises `Cache-Control: public, max-age=15` so edge/CDN/browser
    can dedupe the burst of tickertape fetches."""
    m = int(minutes)
    now = time.time()
    cached = _signups_cache.get(m)
    if cached and (now - cached[0]) < _SIGNUPS_CACHE_TTL_S:
        response.headers["Cache-Control"] = f"public, max-age={_SIGNUPS_CACHE_TTL_S}"
        response.headers["X-Cache"] = "HIT"
        return cached[1]

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()
    count = 0
    try:
        count = await db.users.count_documents({"created_at": {"$gte": cutoff}})
    except Exception as e:
        logger.warning(f"[public/signups-recent] count failed: {e}")
    payload = {
        "minutes": m,
        "count": int(count),
        "since_iso": cutoff,
        "now_iso": datetime.now(timezone.utc).isoformat(),
    }
    _signups_cache[m] = (now, payload)
    response.headers["Cache-Control"] = f"public, max-age={_SIGNUPS_CACHE_TTL_S}"
    response.headers["X-Cache"] = "MISS"
    return payload


@router.get("/public/coaching-tip-of-the-day")
async def public_coaching_tip_of_the_day(response: Response):
    """Return today's curated coaching tip. DB-backed — admins can edit
    via /api/admin/coaching-tips. Rotation is deterministic per UTC day
    over the active tips ordered by `position` asc."""
    await _ensure_tips_seeded()
    active: list[dict[str, Any]] = []
    async for t in db[TIPS_COL].find({"is_active": True}, {"_id": 0}).sort("position", 1):
        active.append(t)

    # Guard: if an admin deactivates every single tip, fall back silently
    # to the hardcoded seed so the tickertape never vanishes in prod.
    source = "db"
    if not active:
        source = "seed_fallback"
        active = [
            {"title": t["title"], "content": t["content"], "tip_id": f"seed-{i:03d}"}
            for i, t in enumerate(PUBLIC_COACHING_TIPS)
        ]

    now = datetime.now(timezone.utc)
    idx = (now.timetuple().tm_yday - 1) % len(active)
    tip = active[idx]
    # Public tip rotates exactly once per UTC day — advertise edge cache.
    response.headers["Cache-Control"] = "public, max-age=900"
    return {
        "title": tip["title"],
        "content": tip["content"],
        "tip_id": tip.get("tip_id") or "",
        "day_iso": now.date().isoformat(),
        "index": idx,
        "total": len(active),
        "source": source,
    }


class TickertapeEvent(BaseModel):
    fact_testid: str = Field(..., min_length=3, max_length=64)
    event_type: Literal["impression", "click"]
    session_id: Optional[str] = Field(None, max_length=64)


@router.post("/public/tickertape-event")
async def public_tickertape_event(body: TickertapeEvent, request: Request):
    """Log a tickertape impression or click. No auth. Used by the
    Welcome page's rotating pill to measure which fact converts best
    — answers the 'which social-proof line actually earns the click'
    question that the admin CTR panel surfaces."""
    # Keep the testid whitelist tight so this endpoint cannot be used as
    # an arbitrary write channel. Every allowed value corresponds to a
    # real fact the tickertape can render.
    allowed = {
        "welcome-tickertape-fact-online",
        "welcome-tickertape-fact-sessions",
        "welcome-tickertape-fact-active",
        "welcome-tickertape-fact-perf",
        "welcome-tickertape-fact-coaches",
        "welcome-tickertape-fact-health",
        "welcome-tickertape-fact-signups",
        "welcome-tickertape-fact-tip",
    }
    if body.fact_testid not in allowed:
        raise HTTPException(status_code=400, detail="Unknown fact_testid")

    doc = {
        "fact_testid": body.fact_testid,
        "event_type": body.event_type,
        "session_id": (body.session_id or "")[:64] or None,
        # Do NOT store IP or UA fingerprints — public endpoint, no PII.
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db[TICKERTAPE_COL].insert_one(doc)
    except Exception as e:
        logger.warning(f"[public/tickertape-event] insert failed: {e}")
        # Fire-and-forget — never fail the public page over telemetry.
    return {"ok": True}


__all__ = ["router", "PUBLIC_COACHING_TIPS", "TIPS_COL", "TICKERTAPE_COL"]
