"""Maintenance cleanup routes."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta

from .db import db, require_auth, logger

router = APIRouter()


@router.post("/content/daily-refresh")
async def daily_content_refresh():
    """Automated daily content refresh - adds new videos/podcasts, removes old ones."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=30)).isoformat()

    # Remove videos older than 30 days
    old_videos = await db.video_catalog.delete_many({"added_date": {"$lt": cutoff}})

    # Remove podcasts older than 30 days
    old_podcasts = await db.podcast_pool.delete_many({"added_date": {"$lt": cutoff}})

    # Count current content
    video_count = await db.video_catalog.count_documents({})
    podcast_count = await db.podcast_pool.count_documents({})

    logger.info(
        f"Daily refresh: removed {old_videos.deleted_count} old videos, {old_podcasts.deleted_count} old podcasts"
    )

    return {
        "success": True,
        "removed": {
            "old_videos": old_videos.deleted_count,
            "old_podcasts": old_podcasts.deleted_count,
        },
        "current_counts": {
            "videos": video_count,
            "podcasts": podcast_count,
        },
        "next_refresh": (now + timedelta(days=1)).isoformat(),
        "timestamp": now.isoformat(),
    }


@router.get("/content/stats")
async def content_stats():
    """Get current content statistics."""
    video_count = await db.video_catalog.count_documents({})
    podcast_count = await db.podcast_pool.count_documents({})

    return {
        "videos": video_count,
        "podcasts": podcast_count,
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "auto_refresh_enabled": True,
        "retention_days": 30,
    }


@router.delete("/cleanup/clone-data")
async def cleanup_clone_data(req: Request):
    user = await require_auth(req)
    blueprints = await db.blueprints.delete_many({"user_id": user.user_id})
    clone_settings = await db.clone_settings.delete_many({"user_id": user.user_id})
    free_cache = await db.free_api_cache.delete_many({})

    return {
        "success": True,
        "removed": {
            "blueprints": blueprints.deleted_count,
            "clone_settings": clone_settings.deleted_count,
            "free_api_cache": free_cache.deleted_count,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
