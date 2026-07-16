"""Native Agent Knowledge Management: curated collections, versioned sources,
connectors, indexing, citation tracking, retrieval quality and governance."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

CONNECTOR_TYPES = {"manual", "url", "mongo_collection"}
CONNECTOR_ALLOWED_COLLECTIONS = {"af_agents", "af_workflows", "af_prompts"}
STOPWORDS = {"the", "and", "for", "with", "that", "this", "are", "was", "you", "your", "from", "have", "has"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> List[str]:
    words = "".join(c if c.isalnum() else " " for c in (text or "").lower()).split()
    return sorted({w for w in words if len(w) > 2 and w not in STOPWORDS})


# ── Collections ──

async def list_collections() -> List[Dict[str, Any]]:
    from routes.db import db

    cols = await db.af_knowledge_collections.find({}, {"_id": 0}).sort("name", 1).to_list(length=200)
    counts: Dict[str, int] = {}
    for row in await db.af_knowledge_sources.aggregate([
        {"$group": {"_id": "$collection_key", "count": {"$sum": 1}}}
    ]).to_list(length=500):
        counts[row["_id"]] = row["count"]
    for col in cols:
        col["source_count"] = counts.get(col["collection_key"], 0)
    return cols


async def upsert_collection(payload: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    key = payload["collection_key"]
    existing = await db.af_knowledge_collections.find_one({"collection_key": key}, {"_id": 0})
    now = _now()
    doc = {
        "collection_key": key,
        "name": payload.get("name", key),
        "description": payload.get("description", ""),
        "category": payload.get("category", "General"),
        "permissions": payload.get("permissions", ["admin"]),
        "governance": payload.get("governance", {"review_required": False, "retention_days": 365}),
        "status": payload.get("status", "active"),
        "version": int(existing.get("version", 0)) + 1 if existing else 1,
        "updated_at": now,
        "updated_by": actor_id,
    }
    if not existing:
        doc["created_at"] = now
    await db.af_knowledge_collections.update_one({"collection_key": key}, {"$set": doc}, upsert=True)
    await log_audit("knowledge_collection_upserted", actor_id, "knowledge_collection", key, {"version": doc["version"]})
    return await db.af_knowledge_collections.find_one({"collection_key": key}, {"_id": 0})


async def delete_collection(collection_key: str, actor_id: str) -> bool:
    from routes.db import db
    from agent_framework.audit import log_audit

    result = await db.af_knowledge_collections.delete_one({"collection_key": collection_key})
    if result.deleted_count:
        await db.af_knowledge_sources.delete_many({"collection_key": collection_key})
        await log_audit("knowledge_collection_deleted", actor_id, "knowledge_collection", collection_key)
        return True
    return False


# ── Sources ──

async def list_sources(collection_key: str = "") -> List[Dict[str, Any]]:
    from routes.db import db

    query = {"collection_key": collection_key} if collection_key else {}
    return await (
        db.af_knowledge_sources.find(query, {"_id": 0, "content": 0, "terms": 0})
        .sort("updated_at", -1).to_list(length=500)
    )


async def _index_source(source_id: str, content: str, sync_status: str) -> None:
    from routes.db import db

    await db.af_knowledge_sources.update_one(
        {"source_id": source_id},
        {"$set": {
            "content": content[:200_000],
            "terms": _tokenize(content[:200_000]),
            "term_count": len(_tokenize(content[:200_000])),
            "sync_status": sync_status,
            "last_synced_at": _now(),
            "updated_at": _now(),
        }},
    )


async def add_source(payload: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    source_type = payload.get("source_type", "manual")
    if source_type not in CONNECTOR_TYPES:
        raise ValueError(f"Invalid source_type. Allowed: {sorted(CONNECTOR_TYPES)}")
    collection = await db.af_knowledge_collections.find_one({"collection_key": payload["collection_key"]}, {"_id": 0})
    if not collection:
        raise KeyError("Knowledge collection not found")
    source_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "source_id": source_id,
        "collection_key": payload["collection_key"],
        "name": payload.get("name", "Untitled source"),
        "source_type": source_type,
        "config": {
            "url": payload.get("url", ""),
            "mongo_collection": payload.get("mongo_collection", ""),
        },
        "sync_status": "pending",
        "citations": 0,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "created_by": actor_id,
    }
    await db.af_knowledge_sources.insert_one(doc)
    if source_type == "manual":
        await _index_source(source_id, payload.get("content", ""), "synced")
    else:
        await sync_source(source_id, actor_id)
    await log_audit("knowledge_source_added", actor_id, "knowledge_source", source_id,
                    {"collection_key": payload["collection_key"], "type": source_type})
    return await db.af_knowledge_sources.find_one({"source_id": source_id}, {"_id": 0, "content": 0, "terms": 0})


async def sync_source(source_id: str, actor_id: str = "system") -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    source = await db.af_knowledge_sources.find_one({"source_id": source_id}, {"_id": 0})
    if not source:
        raise KeyError("Knowledge source not found")
    if source.get("content"):
        await db.af_knowledge_source_versions.insert_one({
            "version_id": str(uuid.uuid4()), "source_id": source_id,
            "content_snapshot": source["content"][:200_000],
            "version": source.get("version", 1),
            "archived_at": _now(),
        })
    try:
        source_type = source["source_type"]
        if source_type == "url":
            import httpx

            url = source.get("config", {}).get("url", "")
            if not url.startswith("https://"):
                raise ValueError("Only https:// URLs are permitted")
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url)
                content = resp.text[:200_000]
        elif source_type == "mongo_collection":
            coll = source.get("config", {}).get("mongo_collection", "")
            if coll not in CONNECTOR_ALLOWED_COLLECTIONS:
                raise PermissionError(f"Collection '{coll}' not in connector allowlist")
            docs = await db[coll].find({}, {"_id": 0, "system_prompt": 0}).limit(200).to_list(length=200)
            content = "\n".join(str(d) for d in docs)[:200_000]
        else:
            content = source.get("content", "")
        await _index_source(source_id, content, "synced")
        await db.af_knowledge_sources.update_one({"source_id": source_id}, {"$inc": {"version": 1}})
    except Exception as exc:
        await db.af_knowledge_sources.update_one(
            {"source_id": source_id},
            {"$set": {"sync_status": "error", "sync_error": str(exc)[:500], "updated_at": _now()}},
        )
        raise
    await log_audit("knowledge_source_synced", actor_id, "knowledge_source", source_id)
    return await db.af_knowledge_sources.find_one({"source_id": source_id}, {"_id": 0, "content": 0, "terms": 0})


async def delete_source(source_id: str, actor_id: str) -> bool:
    from routes.db import db
    from agent_framework.audit import log_audit

    result = await db.af_knowledge_sources.delete_one({"source_id": source_id})
    if result.deleted_count:
        await log_audit("knowledge_source_deleted", actor_id, "knowledge_source", source_id)
        return True
    return False


# ── Retrieval with citations ──

async def search_knowledge(collection_key: str, query: str, limit: int = 5) -> Dict[str, Any]:
    from routes.db import db

    q_terms = set(_tokenize(query))
    mongo_query: Dict[str, Any] = {"sync_status": "synced"}
    if collection_key:
        mongo_query["collection_key"] = collection_key
    sources = await db.af_knowledge_sources.find(
        mongo_query, {"_id": 0, "source_id": 1, "name": 1, "collection_key": 1, "terms": 1, "content": 1}
    ).to_list(length=500)
    scored = []
    for src in sources:
        overlap = q_terms & set(src.get("terms") or [])
        if overlap:
            scored.append((len(overlap), overlap, src))
    scored.sort(key=lambda p: -p[0])
    results = []
    for hits, overlap, src in scored[: max(1, min(limit, 10))]:
        content = src.get("content", "")
        snippet = ""
        lower = content.lower()
        for term in overlap:
            idx = lower.find(term)
            if idx >= 0:
                snippet = content[max(0, idx - 80): idx + 160].strip()
                break
        results.append({
            "source_id": src["source_id"],
            "name": src["name"],
            "collection_key": src["collection_key"],
            "matched_terms": sorted(overlap)[:10],
            "score": hits,
            "snippet": snippet[:300],
            "citation": f"[{src['name']}#{src['source_id'][:8]}]",
        })
        await db.af_knowledge_sources.update_one({"source_id": src["source_id"]}, {"$inc": {"citations": 1}})
    await db.af_knowledge_queries.insert_one({
        "query_id": str(uuid.uuid4()),
        "collection_key": collection_key,
        "query": query[:300],
        "hits": len(results),
        "created_at": _now(),
    })
    return {"query": query, "collection_key": collection_key, "results": results, "total_hits": len(results)}


# ── Overview / retrieval quality ──

async def knowledge_overview() -> Dict[str, Any]:
    from routes.db import db

    collections_total = await db.af_knowledge_collections.count_documents({})
    sources_total = await db.af_knowledge_sources.count_documents({})
    sync_rows = await db.af_knowledge_sources.aggregate([
        {"$group": {"_id": "$sync_status", "count": {"$sum": 1}}}
    ]).to_list(length=10)
    citations = await db.af_knowledge_sources.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$citations"}}}
    ]).to_list(length=1)
    queries_total = await db.af_knowledge_queries.count_documents({})
    quality_rows = await db.af_knowledge_queries.aggregate([
        {"$group": {"_id": None, "avg_hits": {"$avg": "$hits"},
                    "zero_hit": {"$sum": {"$cond": [{"$eq": ["$hits", 0]}, 1, 0]}}}}
    ]).to_list(length=1)
    quality = quality_rows[0] if quality_rows else {}
    return {
        "collections_total": collections_total,
        "sources_total": sources_total,
        "sync_status": {(r["_id"] or "unknown"): r["count"] for r in sync_rows},
        "citations_total": int((citations[0]["total"] if citations else 0) or 0),
        "queries_total": queries_total,
        "retrieval_quality": {
            "avg_hits_per_query": round(float(quality.get("avg_hits") or 0), 2),
            "zero_hit_queries": int(quality.get("zero_hit") or 0),
            "hit_rate_percent": round((1 - (int(quality.get("zero_hit") or 0) / max(1, queries_total))) * 100, 1),
        },
        "connector_types": sorted(CONNECTOR_TYPES),
        "generated_at": _now(),
    }
