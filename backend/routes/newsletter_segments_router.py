"""Subscriber segmentation engine — auto-tags subscribers based on behavior."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from routes.db import db
from routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/newsletter/segments", tags=["newsletter-segments"])

SEGMENT_DEFS = [
    {
        "id": "new_signup",
        "label": "New Signups",
        "description": "Subscribed in the last 7 days",
        "color": "#3B82F6",
        "icon": "sparkles",
    },
    {
        "id": "established",
        "label": "Established",
        "description": "Subscribed 7-30 days ago",
        "color": "#8B5CF6",
        "icon": "people",
    },
    {
        "id": "veteran",
        "label": "Veterans",
        "description": "Subscribed 30+ days ago",
        "color": "#F59E0B",
        "icon": "trophy",
    },
    {
        "id": "active_user",
        "label": "Active Users",
        "description": "Has a platform account and logged in",
        "color": "#10B981",
        "icon": "person-circle",
    },
    {
        "id": "subscriber_only",
        "label": "Subscriber Only",
        "description": "Newsletter only, no platform account",
        "color": "#6B7280",
        "icon": "mail-unread",
    },
    {
        "id": "ai_power_user",
        "label": "AI Power Users",
        "description": "Heavy AI feature usage (10+ requests)",
        "color": "#EF4444",
        "icon": "flash",
    },
    {
        "id": "learning_focused",
        "label": "Learning Focused",
        "description": "Active in Learning Hub content",
        "color": "#06B6D4",
        "icon": "book",
    },
    {
        "id": "coaching_active",
        "label": "Coaching Active",
        "description": "Engaged with coaching tools",
        "color": "#F97316",
        "icon": "fitness",
    },
]


async def compute_segments_for_subscriber(email: str) -> list[str]:
    """Compute segment tags for a single subscriber."""
    now = datetime.now(timezone.utc)
    tags = []

    sub = await db.newsletter_subscribers.find_one({"email": email, "status": "active"}, {"_id": 0, "subscribed_at": 1})
    if not sub:
        return tags

    # Recency segments
    sub_date = datetime.fromisoformat(sub["subscribed_at"]) if sub.get("subscribed_at") else now
    days_since = (now - sub_date).days
    if days_since <= 7:
        tags.append("new_signup")
    elif days_since <= 30:
        tags.append("established")
    else:
        tags.append("veteran")

    # Platform account check
    user = await db.users.find_one({"email": email}, {"_id": 0, "email": 1})
    if user:
        tags.append("active_user")
    else:
        tags.append("subscriber_only")
        return tags  # No platform data for non-users

    # AI usage
    ai_count = 0
    if "ai_requests" in await db.list_collection_names():
        ai_count = await db.ai_requests.count_documents({"user_email": email})
    if ai_count >= 10:
        tags.append("ai_power_user")

    # Learning hub
    learning_count = 0
    if "content_interactions" in await db.list_collection_names():
        learning_count = await db.content_interactions.count_documents({"user_email": email, "type": "learning"})
    if learning_count >= 5:
        tags.append("learning_focused")

    # Coaching
    coaching_count = 0
    if "coaching_sessions" in await db.list_collection_names():
        coaching_count = await db.coaching_sessions.count_documents({"user_email": email})
    if coaching_count >= 3:
        tags.append("coaching_active")

    return tags


async def refresh_all_segments():
    """Nightly job: recompute segment tags for all active subscribers."""
    logger.info("Refreshing subscriber segments...")
    subs = await db.newsletter_subscribers.find({"status": "active"}, {"_id": 0, "email": 1}).to_list(length=100000)

    updated = 0
    for sub in subs:
        tags = await compute_segments_for_subscriber(sub["email"])
        await db.newsletter_subscribers.update_one(
            {"email": sub["email"]},
            {"$set": {"segments": tags, "segments_updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        updated += 1

    logger.info(f"Segment refresh complete: {updated} subscribers updated.")
    return {"updated": updated}


@router.get("")
async def list_segments(user=Depends(get_current_user)):
    """Get all segment definitions with subscriber counts."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Ensure segments are computed
    untagged = await db.newsletter_subscribers.count_documents(
        {"status": "active", "$or": [{"segments": {"$exists": False}}, {"segments": []}]}
    )
    if untagged > 0:
        await refresh_all_segments()

    segments = []
    total_active = await db.newsletter_subscribers.count_documents({"status": "active"})

    for seg in SEGMENT_DEFS:
        count = await db.newsletter_subscribers.count_documents({"status": "active", "segments": seg["id"]})
        segments.append(
            {
                **seg,
                "count": count,
                "percentage": round((count / max(total_active, 1)) * 100, 1),
            }
        )

    return {
        "segments": segments,
        "total_subscribers": total_active,
    }


@router.get("/{segment_id}/subscribers")
async def get_segment_subscribers(segment_id: str, user=Depends(get_current_user)):
    """Get subscribers in a specific segment."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    valid_ids = [s["id"] for s in SEGMENT_DEFS]
    if segment_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Segment not found")

    subs = (
        await db.newsletter_subscribers.find(
            {"status": "active", "segments": segment_id},
            {"_id": 0, "email": 1, "subscribed_at": 1, "source": 1, "segments": 1},
        )
        .sort("subscribed_at", -1)
        .to_list(length=100)
    )

    seg_def = next(s for s in SEGMENT_DEFS if s["id"] == segment_id)

    return {
        "segment": seg_def,
        "subscribers": subs,
        "count": len(subs),
    }
