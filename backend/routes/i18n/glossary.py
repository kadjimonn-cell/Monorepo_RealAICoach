"""i18n glossary management."""

from fastapi import HTTPException, Request
import re
from datetime import datetime, timezone

from ..db import db

from .helpers import router, _write_locale_updates

@router.get("/glossary")
async def get_glossary(request: Request):
    """Get translation glossary entries. Optional filters: lang, search, page."""
    lang = request.query_params.get("lang", "")
    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", "1"))
    limit = int(request.query_params.get("limit", "50"))
    skip = (page - 1) * limit

    query = {}
    if lang:
        query["lang"] = lang
    if search:
        query["$or"] = [
            {"key": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"value": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]

    total = await db.translation_glossary.count_documents(query)
    entries = []
    async for doc in db.translation_glossary.find(query, {"_id": 0}).sort("key", 1).skip(skip).limit(limit):
        entries.append(doc)
    return {"entries": entries, "total": total, "page": page, "limit": limit}


@router.post("/glossary")
async def add_glossary_entry(request: Request):
    """Add or update a glossary entry (manual override)."""
    body = await request.json()
    key = body.get("key", "").strip()
    lang = body.get("lang", "").strip()
    value = body.get("value", "").strip()
    if not key or not lang or not value:
        raise HTTPException(status_code=400, detail="key, lang, and value are required")

    now = datetime.now(timezone.utc).isoformat()
    await db.translation_glossary.update_one(
        {"key": key, "lang": lang},
        {"$set": {"key": key, "lang": lang, "value": value, "source": "manual", "updated_at": now}},
        upsert=True,
    )
    return {"success": True, "key": key, "lang": lang}


@router.delete("/glossary")
async def delete_glossary_entry(request: Request):
    """Delete a glossary entry."""
    body = await request.json()
    key = body.get("key", "").strip()
    lang = body.get("lang", "").strip()
    if not key or not lang:
        raise HTTPException(status_code=400, detail="key and lang are required")
    result = await db.translation_glossary.delete_one({"key": key, "lang": lang})
    return {"success": True, "deleted": result.deleted_count}


@router.get("/glossary/stats")
async def glossary_stats():
    """Get glossary statistics: total entries, per-language counts, sources."""
    pipeline = [
        {"$group": {"_id": {"lang": "$lang", "source": "$source"}, "count": {"$sum": 1}}},
    ]
    results = {}
    total = 0
    async for doc in db.translation_glossary.aggregate(pipeline):
        lang = doc["_id"]["lang"]
        source = doc["_id"]["source"]
        if lang not in results:
            results[lang] = {"total": 0, "manual": 0, "auto": 0}
        results[lang]["total"] += doc["count"]
        if source == "manual":
            results[lang]["manual"] += doc["count"]
        else:
            results[lang]["auto"] += doc["count"]
        total += doc["count"]
    return {"total_entries": total, "by_language": results}


@router.post("/glossary/apply")
async def apply_glossary_to_file(request: Request):
    """Apply glossary overrides to locale files."""
    body = await request.json()
    lang = body.get("lang")
    if not lang:
        raise HTTPException(status_code=400, detail="lang is required")

    # Get glossary entries for this language
    entries = {}
    async for doc in db.translation_glossary.find({"lang": lang, "source": "manual"}, {"_id": 0}):
        entries[doc["key"]] = doc["value"]

    if not entries:
        return {"success": True, "applied": 0, "message": "No manual overrides to apply"}

    try:
        applied = _write_locale_updates(lang, entries, append_missing=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Language {lang} locale file not found")

    return {"success": True, "applied": applied, "total_overrides": len(entries)}



