"""ASO Keyword Tracking — CRUD + live ranking refresh from App Store & Google Play.

Split from aso_unified.py for modularity. All endpoints under /admin/aso-unified/keywords.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/aso-unified/keywords", tags=["ASO Keywords"])


@router.get("")
async def get_tracked_keywords(request: Request):
    """Get all tracked keywords with rankings."""
    keywords = await db.aso_keywords.find({}, {"_id": 0}).sort("keyword", 1).to_list(200)
    for kw in keywords:
        if hasattr(kw.get("updated_at"), "isoformat"):
            kw["updated_at"] = kw["updated_at"].isoformat()
    return {"keywords": keywords, "total": len(keywords)}


@router.post("")
async def add_keyword(request: Request):
    """Add a keyword to track — fetches REAL rankings from App Store & Google Play."""
    body = await request.json()
    keyword = body.get("keyword", "").strip().lower()
    if not keyword:
        raise HTTPException(400, "keyword is required")

    existing = await db.aso_keywords.find_one({"keyword": keyword})
    if existing:
        raise HTTPException(409, "keyword already tracked")

    now = datetime.now(timezone.utc)

    # Fetch REAL ranking data from both stores
    try:
        from services.aso_keyword_service import get_real_keyword_data
        real_data = await get_real_keyword_data(keyword)
        apple_data = real_data["apple"]
        google_data = real_data["google"]
        competitors = real_data["competitors"]
        data_source = "live"
    except Exception as e:
        logger.warning(f"Real ASO data fetch failed for '{keyword}', using defaults: {e}")
        apple_data = {"rank": 0, "total_results": 0, "difficulty": 0, "search_volume": "low", "top_results": []}
        google_data = {"rank": 0, "total_results": 0, "difficulty": 0, "search_volume": "low", "top_results": []}
        competitors = [
            {"name": "BetterUp", "apple_rank": 0, "google_rank": 0},
            {"name": "CoachHub", "apple_rank": 0, "google_rank": 0},
            {"name": "Torch", "apple_rank": 0, "google_rank": 0},
        ]
        data_source = "offline"

    doc = {
        "keyword": keyword,
        "added_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "data_source": data_source,
        "apple": {
            "rank": apple_data["rank"],
            "prev_rank": apple_data["rank"],
            "difficulty": apple_data["difficulty"],
            "search_volume": apple_data["search_volume"],
            "total_results": apple_data.get("total_results", 0),
            "top_results": apple_data.get("top_results", []),
        },
        "google": {
            "rank": google_data["rank"],
            "prev_rank": google_data["rank"],
            "difficulty": google_data["difficulty"],
            "search_volume": google_data["search_volume"],
            "total_results": google_data.get("total_results", 0),
            "top_results": google_data.get("top_results", []),
        },
        "competitors": competitors,
    }
    await db.aso_keywords.insert_one(doc)
    doc.pop("_id", None)

    # Broadcast keyword addition via WebSocket
    await _broadcast_aso_update("keyword_added", keyword)

    return doc


@router.post("/refresh")
async def refresh_keyword_rankings(request: Request):
    """Refresh rankings for all tracked keywords with REAL data from stores."""
    now = datetime.now(timezone.utc)
    keywords = await db.aso_keywords.find({}).to_list(200)
    updated = 0
    errors = []

    for kw in keywords:
        prev_apple = kw.get("apple", {}).get("rank", 0)
        prev_google = kw.get("google", {}).get("rank", 0)

        try:
            from services.aso_keyword_service import get_real_keyword_data
            real_data = await get_real_keyword_data(kw["keyword"])
            apple_data = real_data["apple"]
            google_data = real_data["google"]
            competitors = real_data["competitors"]

            await db.aso_keywords.update_one({"keyword": kw["keyword"]}, {"$set": {
                "updated_at": now.isoformat(),
                "data_source": "live",
                "apple.prev_rank": prev_apple,
                "apple.rank": apple_data["rank"],
                "apple.difficulty": apple_data["difficulty"],
                "apple.search_volume": apple_data["search_volume"],
                "apple.total_results": apple_data.get("total_results", 0),
                "apple.top_results": apple_data.get("top_results", []),
                "google.prev_rank": prev_google,
                "google.rank": google_data["rank"],
                "google.difficulty": google_data["difficulty"],
                "google.search_volume": google_data["search_volume"],
                "google.total_results": google_data.get("total_results", 0),
                "google.top_results": google_data.get("top_results", []),
                "competitors": competitors,
            }})
            updated += 1

            # Check and send ranking alerts
            from routes.aso_alerts import check_and_send_ranking_alerts
            await check_and_send_ranking_alerts(
                kw["keyword"], prev_apple, apple_data["rank"],
                prev_google, google_data["rank"]
            )
        except Exception as e:
            logger.error(f"Failed to refresh keyword '{kw['keyword']}': {e}")
            errors.append({"keyword": kw["keyword"], "error": str(e)})

    # Log history
    await db.aso_keyword_history.insert_one({
        "refreshed_at": now.isoformat(),
        "keywords_updated": updated,
        "errors": len(errors),
    })

    # Broadcast refresh completion via WebSocket
    await _broadcast_aso_update("keywords_refreshed", f"{updated} keywords updated")

    return {
        "status": "refreshed",
        "keywords_updated": updated,
        "errors": errors,
        "data_source": "live",
        "timestamp": now.isoformat(),
    }


@router.get("/schedule-status")
async def get_keyword_schedule_status(request: Request):
    """Get the status of the auto-refresh scheduler job."""
    last_refresh = await db.aso_keyword_history.find_one(
        {}, {"_id": 0}, sort=[("refreshed_at", -1)]
    )
    keyword_count = await db.aso_keywords.count_documents({})
    return {
        "schedule": "daily at 06:00 UTC",
        "last_refresh": last_refresh,
        "tracked_keywords": keyword_count,
        "data_source": "live (iTunes Search API + Google Play Scraper)",
    }


# ─── Dynamic keyword routes ({keyword} param) ───

@router.delete("/{keyword}")
async def remove_keyword(request: Request, keyword: str):
    """Remove a tracked keyword."""
    result = await db.aso_keywords.delete_one({"keyword": keyword.lower()})
    if result.deleted_count == 0:
        raise HTTPException(404, "keyword not found")

    await _broadcast_aso_update("keyword_removed", keyword.lower())
    return {"status": "deleted", "keyword": keyword.lower()}


@router.get("/{keyword}/details")
async def get_keyword_details(request: Request, keyword: str):
    """Get detailed search results for a specific keyword — shows top apps in both stores."""
    kw_doc = await db.aso_keywords.find_one({"keyword": keyword.lower()}, {"_id": 0})
    if not kw_doc:
        raise HTTPException(404, "keyword not found")

    apple_top = kw_doc.get("apple", {}).get("top_results", [])
    google_top = kw_doc.get("google", {}).get("top_results", [])

    if not apple_top and not google_top:
        try:
            from services.aso_keyword_service import get_real_keyword_data
            real_data = await get_real_keyword_data(keyword.lower())
            apple_top = real_data["apple"].get("top_results", [])
            google_top = real_data["google"].get("top_results", [])
        except Exception:
            pass

    return {
        "keyword": keyword.lower(),
        "apple_top_results": apple_top,
        "google_top_results": google_top,
        "updated_at": kw_doc.get("updated_at"),
        "data_source": kw_doc.get("data_source", "unknown"),
    }


@router.get("/{keyword}/history")
async def get_keyword_ranking_history(request: Request, keyword: str):
    """Get ranking history for a keyword (trend data for charts)."""
    kw_doc = await db.aso_keywords.find_one({"keyword": keyword.lower()})
    if not kw_doc:
        raise HTTPException(404, "keyword not found")

    history = await db.aso_keyword_ranking_history.find(
        {"keyword": keyword.lower()}, {"_id": 0}
    ).sort("timestamp", 1).to_list(365)

    return {
        "keyword": keyword.lower(),
        "history": history,
        "total_points": len(history),
    }


async def _broadcast_aso_update(action: str, detail: str = ""):
    """Broadcast ASO data update to connected WebSocket clients."""
    try:
        from utils.ws_manager import ws_manager
        if ws_manager.aso_listeners:
            # Fetch fresh keyword data
            keywords = await db.aso_keywords.find({}, {"_id": 0}).sort("keyword", 1).to_list(200)
            for kw in keywords:
                if hasattr(kw.get("updated_at"), "isoformat"):
                    kw["updated_at"] = kw["updated_at"].isoformat()

            keyword_count = len(keywords)
            schedule = await db.aso_keyword_history.find_one(
                {}, {"_id": 0}, sort=[("refreshed_at", -1)]
            )

            await ws_manager.broadcast_aso({
                "type": "aso:update",
                "action": action,
                "detail": detail,
                "keywords": keywords,
                "total": keyword_count,
                "last_refresh": schedule,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logger.error(f"ASO WS broadcast failed: {e}")
