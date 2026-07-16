"""Google Play Console Routes — Real Google Play Developer API integration.

Endpoints:
- GET  /api/admin/google-play/status                    — Connection status
- GET  /api/admin/google-play/reviews/{package_name}    — List reviews
- POST /api/admin/google-play/reviews/{package_name}/reply — Reply to review
- GET  /api/admin/google-play/app/{package_name}        — App details
- GET  /api/admin/google-play/dashboard                 — Combined dashboard
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/google-play", tags=["Google Play Console"])


@router.get("/status")
async def play_status(request: Request):
    """Test Google Play Developer API connection."""
    from services.google_play import get_connection_status
    status = await get_connection_status()
    return status


@router.get("/reviews/{package_name}")
async def list_reviews(request: Request, package_name: str, max_results: int = Query(20, ge=1, le=100)):
    """List reviews for an app."""
    from services.google_play import list_reviews as _list
    result = await _list(package_name, max_results)
    # Cache in DB
    if result.get("status") == "ok" and result.get("reviews"):
        doc = {"package_name": package_name, "reviews": result["reviews"], "fetched_at": datetime.now(timezone.utc)}
        await db.google_play_reviews.replace_one(
            {"package_name": package_name}, doc, upsert=True
        )
    return result


class ReviewReply(BaseModel):
    review_id: str
    reply_text: str


@router.post("/reviews/{package_name}/reply")
async def reply_review(request: Request, package_name: str, body: ReviewReply):
    """Reply to a user review."""
    from services.google_play import reply_to_review
    result = await reply_to_review(package_name, body.review_id, body.reply_text)
    return result


@router.get("/app/{package_name}")
async def app_details(request: Request, package_name: str):
    """Get app details and listings."""
    from services.google_play import get_app_details
    result = await get_app_details(package_name)
    if result.get("status") == "ok":
        doc = {**result, "fetched_at": datetime.now(timezone.utc)}
        doc.pop("_id", None)
        await db.google_play_apps.replace_one(
            {"package_name": package_name}, doc, upsert=True
        )
    return result


@router.get("/dashboard")
async def play_dashboard(request: Request):
    """Combined Google Play dashboard — connection status & cached data."""
    from services.google_play import get_connection_status

    status = await get_connection_status()

    # Get cached reviews
    cached_reviews = await db.google_play_reviews.find(
        {}, {"_id": 0}
    ).sort("fetched_at", -1).limit(5).to_list(5)
    for r in cached_reviews:
        if hasattr(r.get("fetched_at"), "isoformat"):
            r["fetched_at"] = r["fetched_at"].isoformat()

    # Get cached app details
    cached_apps = await db.google_play_apps.find(
        {}, {"_id": 0}
    ).sort("fetched_at", -1).limit(10).to_list(10)
    for a in cached_apps:
        if hasattr(a.get("fetched_at"), "isoformat"):
            a["fetched_at"] = a["fetched_at"].isoformat()

    return {
        "connection": status,
        "cached_reviews": cached_reviews,
        "cached_apps": cached_apps,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
