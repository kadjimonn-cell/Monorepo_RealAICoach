"""Admin-only tickertape CTR analytics.

Reads the `tickertape_events` collection the public POST /public/tickertape-event
writes to, and returns per-fact impression/click/CTR rollups so admins
can see which social-proof line on the Welcome page converts best.

    GET /api/admin/tickertape-analytics?days=7
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query, Request

from routes.db import db, require_admin
from routes.public_social_proof import TICKERTAPE_COL

logger = logging.getLogger(__name__)
router = APIRouter()


# Human-friendly labels keyed by tickertape fact_testid — single source
# of truth for the analytics card.
FACT_LABELS: dict[str, str] = {
    "welcome-tickertape-fact-online": "Professionals online right now",
    "welcome-tickertape-fact-sessions": "AI coaching sessions today",
    "welcome-tickertape-fact-active": "Active professionals this week",
    "welcome-tickertape-fact-perf": "Performance boost reported",
    "welcome-tickertape-fact-coaches": "Certified coaches",
    "welcome-tickertape-fact-health": "AI infrastructure healthy",
    "welcome-tickertape-fact-signups": "Signed up in last 60 min",
    "welcome-tickertape-fact-tip": "Tip of the day",
}


@router.get("/admin/tickertape-analytics")
async def admin_tickertape_analytics(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Look-back window in days."),
):
    await require_admin(request)
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()

    # Aggregate impressions + clicks per fact in a single pass so a noisy
    # tickertape doesn't fan out into N*2 round-trips.
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"fact_testid": "$fact_testid", "event_type": "$event_type"},
            "count": {"$sum": 1},
        }},
    ]
    impressions: dict[str, int] = {}
    clicks: dict[str, int] = {}
    try:
        async for row in db[TICKERTAPE_COL].aggregate(pipeline):
            k = row["_id"]
            fid = k.get("fact_testid")
            et = k.get("event_type")
            n = int(row.get("count", 0))
            if not fid:
                continue
            if et == "impression":
                impressions[fid] = impressions.get(fid, 0) + n
            elif et == "click":
                clicks[fid] = clicks.get(fid, 0) + n
    except Exception as e:
        logger.warning(f"[admin_tickertape_analytics] aggregate failed: {e}")

    fact_ids = sorted(set(impressions.keys()) | set(clicks.keys()) | set(FACT_LABELS.keys()))
    per_fact: list[dict[str, Any]] = []
    for fid in fact_ids:
        imp = int(impressions.get(fid, 0))
        clk = int(clicks.get(fid, 0))
        ctr = round((clk / imp * 100), 2) if imp > 0 else 0.0
        per_fact.append({
            "fact_testid": fid,
            "label": FACT_LABELS.get(fid, fid),
            "impressions": imp,
            "clicks": clk,
            "ctr_pct": ctr,
        })

    # Rank winners by absolute clicks (what actually earned the action),
    # then by CTR as the tiebreaker.
    per_fact.sort(key=lambda r: (-r["clicks"], -r["ctr_pct"]))
    total_imp = sum(r["impressions"] for r in per_fact)
    total_clk = sum(r["clicks"] for r in per_fact)
    overall_ctr = round((total_clk / total_imp * 100), 2) if total_imp > 0 else 0.0

    return {
        "window_days": int(days),
        "since_iso": since,
        "per_fact": per_fact,
        "totals": {
            "impressions": total_imp,
            "clicks": total_clk,
            "ctr_pct": overall_ctr,
        },
    }


__all__ = ["router"]
