"""Changelog / What's New — fully automated enterprise changelog system."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from .db import db, EMERGENT_LLM_KEY, logger, get_current_user, require_admin
import uuid

router = APIRouter(prefix="/changelog", tags=["changelog"])

# ── Models ──


class ChangelogEntryCreate(BaseModel):
    title: str
    description: str
    category: str = "feature"  # feature | improvement | fix | security
    version: Optional[str] = None
    highlights: List[str] = []
    is_published: bool = True


class ChangelogEntryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    version: Optional[str] = None
    highlights: Optional[List[str]] = None
    is_published: Optional[bool] = None


# ── Helpers ──


def _serialize(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


CATEGORY_CONFIG = {
    "feature": {"label": "New Feature", "color": "#3B82F6", "icon": "rocket"},
    "improvement": {"label": "Improvement", "color": "#8B5CF6", "icon": "trending-up"},
    "fix": {"label": "Bug Fix", "color": "#10B981", "icon": "build"},
    "security": {"label": "Security", "color": "#EF4444", "icon": "shield-checkmark"},
}

# ── Admin CRUD ──


@router.post("/entries")
async def create_entry(body: ChangelogEntryCreate, request: Request):
    user = await require_admin(request)
    entry = {
        "entry_id": f"cl_{uuid.uuid4().hex[:12]}",
        "title": body.title,
        "description": body.description,
        "category": body.category,
        "version": body.version or "latest",
        "highlights": body.highlights,
        "is_published": body.is_published,
        "created_by": user.user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.changelog_entries.insert_one(entry)
    return _serialize(entry)


@router.get("/entries")
async def list_entries(request: Request, page: int = 1, limit: int = 20, published_only: bool = False):
    user = await get_current_user(request)
    query = {}
    if published_only or not user.is_admin:
        query["is_published"] = True
    total = await db.changelog_entries.count_documents(query)
    entries = (
        await db.changelog_entries.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    return {"entries": entries, "total": total, "page": page, "pages": max(1, (total + limit - 1) // limit)}


@router.put("/entries/{entry_id}")
async def update_entry(entry_id: str, body: ChangelogEntryUpdate, request: Request):
    await require_admin(request)
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.changelog_entries.update_one({"entry_id": entry_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Entry not found")
    entry = await db.changelog_entries.find_one({"entry_id": entry_id}, {"_id": 0})
    return entry


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str, request: Request):
    await require_admin(request)
    result = await db.changelog_entries.delete_one({"entry_id": entry_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Entry not found")
    return {"status": "deleted"}


# ── User-facing: Latest unread entries ──


@router.get("/latest")
async def get_latest_entries(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    user_id = user.user_id

    # Get user's last seen timestamp
    seen_doc = await db.user_changelog_seen.find_one({"user_id": user_id}, {"_id": 0})
    last_seen = seen_doc.get("last_seen_at") if seen_doc else None

    query = {"is_published": True}
    if last_seen:
        query["created_at"] = {"$gt": last_seen}

    unread = await db.changelog_entries.find(query, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    total_unread = await db.changelog_entries.count_documents(query)

    # Also get recent entries (last 30 days) for the full changelog view
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent = (
        await db.changelog_entries.find({"is_published": True, "created_at": {"$gte": thirty_days_ago}}, {"_id": 0})
        .sort("created_at", -1)
        .limit(50)
        .to_list(50)
    )

    return {
        "unread": unread,
        "unread_count": total_unread,
        "recent": recent,
        "last_seen_at": last_seen,
        "categories": CATEGORY_CONFIG,
    }


@router.get("")
@router.get("/")
async def changelog_public_index(limit: int = 10):
    """Public compatibility endpoint for legacy /api/changelog checks."""
    safe_limit = min(max(limit, 1), 50)
    entries = (
        await db.changelog_entries.find({"is_published": True}, {"_id": 0})
        .sort("created_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )
    return {
        "entries": entries,
        "count": len(entries),
        "source": "public_index",
    }


@router.post("/mark-seen")
async def mark_seen(request: Request):
    user = await get_current_user(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.user_changelog_seen.update_one(
        {"user_id": user.user_id},
        {"$set": {"last_seen_at": now, "updated_at": now}},
        upsert=True,
    )
    return {"status": "ok", "last_seen_at": now}


# ── AI Auto-Generation ──


@router.post("/auto-generate")
async def auto_generate_entries(request: Request):
    """AI-powered auto-generation of changelog entries from system metrics."""
    await require_admin(request)

    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "LLM key not configured")

    # Gather system metrics for the AI
    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # Collect real platform metrics
    metrics = {}
    try:
        metrics["total_users"] = await db.users.count_documents({})
        metrics["new_users_7d"] = await db.users.count_documents({"created_at": {"$gte": seven_days_ago}})
        metrics["total_referrals"] = await db.referrals.count_documents({})
        metrics["new_referrals_7d"] = await db.referrals.count_documents({"created_at": {"$gte": seven_days_ago}})
        metrics["total_tickets"] = await db.support_tickets.count_documents({})
        metrics["resolved_tickets_7d"] = await db.support_tickets.count_documents(
            {"status": "resolved", "updated_at": {"$gte": seven_days_ago}}
        )
        metrics["nova_conversations_7d"] = await db.nova_conversations.count_documents(
            {"created_at": {"$gte": seven_days_ago}}
        )
        metrics["faq_searches_7d"] = await db.faq_searches.count_documents({"timestamp": {"$gte": seven_days_ago}})
        metrics["id_verifications"] = await db.id_verifications.count_documents({})
        metrics["job_applications"] = await db.job_applications.count_documents({})
    except Exception as e:
        logger.warning(f"Changelog metrics collection error: {e}")

    # Get existing entries to avoid duplicates
    existing = await db.changelog_entries.find(
        {"created_at": {"$gte": seven_days_ago}}, {"_id": 0, "title": 1}
    ).to_list(50)
    existing_titles = [e["title"] for e in existing]

    # Use LLM to generate entries
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"changelog-gen-{uuid.uuid4().hex[:8]}",
            system_message="""You are a product manager writing changelog entries for an enterprise referral & coaching platform called RealAICoach.

Generate 3-5 professional changelog entries based on the platform metrics provided. Each entry should:
- Have a concise, compelling title
- Include a 1-2 sentence description
- Be categorized as: feature, improvement, fix, or security
- Include 2-3 highlight bullet points
- Feel authentic and professional (not generic)

IMPORTANT: Do NOT duplicate these existing entries: """
            + str(existing_titles)
            + """

Respond ONLY with valid JSON array like:
[
  {
    "title": "...",
    "description": "...",
    "category": "feature|improvement|fix|security",
    "highlights": ["...", "...", "..."]
  }
]""",
        ).with_model("openai", "gpt-4o")

        prompt = f"""Platform metrics for the last 7 days:
- Total users: {metrics.get("total_users", "N/A")}
- New users (7d): {metrics.get("new_users_7d", "N/A")}
- Referrals (total/new 7d): {metrics.get("total_referrals", "N/A")}/{metrics.get("new_referrals_7d", "N/A")}
- Support tickets (total/resolved 7d): {metrics.get("total_tickets", "N/A")}/{metrics.get("resolved_tickets_7d", "N/A")}
- Nova AI conversations (7d): {metrics.get("nova_conversations_7d", "N/A")}
- FAQ searches (7d): {metrics.get("faq_searches_7d", "N/A")}
- ID verifications: {metrics.get("id_verifications", "N/A")}
- Job applications: {metrics.get("job_applications", "N/A")}

Generate changelog entries that reflect real improvements, features, and fixes for this enterprise platform.
Current date: {now.strftime("%B %d, %Y")}"""

        response = await chat.send_message(UserMessage(text=prompt))

        import json

        # Extract JSON from response
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        entries_data = json.loads(text)

        created = []
        version = f"v{now.strftime('%Y.%m.%d')}"
        for ed in entries_data:
            if ed.get("title") in existing_titles:
                continue
            entry = {
                "entry_id": f"cl_{uuid.uuid4().hex[:12]}",
                "title": ed["title"],
                "description": ed.get("description", ""),
                "category": ed.get("category", "feature"),
                "version": version,
                "highlights": ed.get("highlights", []),
                "is_published": False,  # Draft by default, admin reviews
                "created_by": "ai_auto_generator",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "ai_generated": True,
            }
            await db.changelog_entries.insert_one(entry)
            created.append(_serialize(entry))

        return {"status": "ok", "generated": len(created), "entries": created}

    except Exception as e:
        logger.error(f"Changelog AI generation error: {e}")
        raise HTTPException(500, f"AI generation failed: {str(e)}")


# ── Stats (Admin) ──


@router.get("/stats")
async def get_changelog_stats(request: Request):
    await require_admin(request)
    total = await db.changelog_entries.count_documents({})
    published = await db.changelog_entries.count_documents({"is_published": True})
    drafts = await db.changelog_entries.count_documents({"is_published": False})
    ai_generated = await db.changelog_entries.count_documents({"ai_generated": True})

    # Category breakdown
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]
    cat_breakdown = await db.changelog_entries.aggregate(pipeline).to_list(10)

    # Users who've seen changelog
    seen_count = await db.user_changelog_seen.count_documents({})

    return {
        "total": total,
        "published": published,
        "drafts": drafts,
        "ai_generated": ai_generated,
        "seen_by_users": seen_count,
        "category_breakdown": {c["_id"]: c["count"] for c in cat_breakdown if c["_id"]},
    }


# ── Bulk Publish ──


@router.post("/bulk-publish")
async def bulk_publish(request: Request):
    """Publish all draft entries."""
    await require_admin(request)
    now = datetime.now(timezone.utc).isoformat()
    result = await db.changelog_entries.update_many(
        {"is_published": False}, {"$set": {"is_published": True, "updated_at": now}}
    )
    return {"status": "ok", "published_count": result.modified_count}
