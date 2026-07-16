"""Session Replay — record and replay user sessions for UBA analysis."""

from fastapi import APIRouter, Query, Request
from datetime import datetime, timezone, timedelta
import json
from routes.db import db, require_admin, get_current_user
from observability.request_context import extract_request_observability_context

router = APIRouter(prefix="/admin/session-replay", tags=["Session Replay"])


@router.get("/sessions")
async def list_replay_sessions(
    req: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    user_id: str = Query(""),
    days: int = Query(7, ge=1, le=30),
):
    """List recorded user sessions available for replay."""
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query: dict = {"started_at": {"$gte": cutoff}}
    if user_id:
        query["user_id"] = user_id

    total = await db.session_recordings.count_documents(query)
    skip = (page - 1) * limit
    sessions = []
    async for doc in db.session_recordings.find(query, {"_id": 0}).sort("started_at", -1).skip(skip).limit(limit):
        sessions.append(doc)

    return {"sessions": sessions, "total": total, "page": page, "pages": max(1, (total + limit - 1) // limit)}


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, req: Request):
    """Get full replay data for a specific session."""
    await require_admin(req)
    session = await db.session_recordings.find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        return {"error": "Session not found"}

    events = []
    async for doc in (
        db.session_replay_events.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", 1).limit(5000)
    ):
        events.append(doc)

    return {"session": session, "events": events}


@router.get("/stats")
async def replay_stats(req: Request, days: int = Query(7, ge=1, le=30)):
    """Get session replay statistics."""
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    total_sessions = await db.session_recordings.count_documents({"started_at": {"$gte": cutoff}})
    unique_users = len(await db.session_recordings.distinct("user_id", {"started_at": {"$gte": cutoff}}))

    avg_duration = 0
    async for doc in db.session_recordings.aggregate(
        [
            {"$match": {"started_at": {"$gte": cutoff}, "duration_seconds": {"$gt": 0}}},
            {"$group": {"_id": None, "avg": {"$avg": "$duration_seconds"}}},
        ]
    ):
        avg_duration = round(doc["avg"], 1)

    top_pages = []
    async for doc in db.session_replay_events.aggregate(
        [
            {"$match": {"timestamp": {"$gte": cutoff}, "type": "navigate"}},
            {"$group": {"_id": "$data.url", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
    ):
        top_pages.append({"page": doc["_id"], "visits": doc["count"]})

    return {
        "total_sessions": total_sessions,
        "unique_users": unique_users,
        "avg_duration_seconds": avg_duration,
        "top_pages": top_pages,
    }


# --- Client-side recording endpoint (non-admin) ---


async def _parse_loose_json_body(req: Request) -> dict:
    try:
        payload = await req.json()
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    try:
        raw = (await req.body()).decode("utf-8", errors="ignore").strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@router.post("/record")
async def record_session_events(req: Request):
    """Receive session replay events from the frontend recorder."""
    user = await get_current_user(req)
    if not user:
        return {"ok": False}

    body = await _parse_loose_json_body(req)
    obs_ctx = extract_request_observability_context(req)
    session_id = body.get("session_id", "")
    events = body.get("events", [])

    if not session_id or not events:
        return {"ok": False}

    # Upsert session recording
    now = datetime.now(timezone.utc).isoformat()
    await db.session_recordings.update_one(
        {"session_id": session_id},
        {
            "$setOnInsert": {
                "session_id": session_id,
                "user_id": user.user_id,
                "user_email": user.email,
                "started_at": now,
            },
            "$set": {
                "last_event_at": now,
                "correlation_id": str(getattr(req.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
                "trace_id": str(getattr(req.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
                "span_id": str(getattr(req.state, "span_id", "") or obs_ctx.get("span_id") or ""),
                "request_session_id": str(getattr(req.state, "session_id", "") or obs_ctx.get("session_id") or ""),
            },
            "$inc": {"event_count": len(events)},
        },
        upsert=True,
    )

    # Store events
    docs = []
    for e in events[:100]:
        docs.append(
            {
                "session_id": session_id,
                "user_id": user.user_id,
                "type": e.get("type", "unknown"),
                "data": e.get("data", {}),
                "correlation_id": str(getattr(req.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
                "trace_id": str(getattr(req.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
                "span_id": str(getattr(req.state, "span_id", "") or obs_ctx.get("span_id") or ""),
                "request_session_id": str(getattr(req.state, "session_id", "") or obs_ctx.get("session_id") or ""),
                "timestamp": e.get("timestamp", now),
            }
        )
    if docs:
        await db.session_replay_events.insert_many(docs)

    return {"ok": True, "recorded": len(docs)}


@router.post("/end")
async def end_session(req: Request):
    """Mark a session recording as complete."""
    user = await get_current_user(req)
    if not user:
        return {"ok": False}

    body = await _parse_loose_json_body(req)
    session_id = body.get("session_id", "")
    if not session_id:
        return {"ok": False}

    session = await db.session_recordings.find_one({"session_id": session_id, "user_id": user.user_id})
    if not session:
        return {"ok": False}

    started = session.get("started_at", "")
    duration = 0
    if started:
        try:
            start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            duration = (datetime.now(timezone.utc) - start_dt).total_seconds()
        except Exception:
            pass

    await db.session_recordings.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(duration),
                "status": "complete",
            }
        },
    )
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, req: Request):
    """Delete a session and all its events (admin only)."""
    await require_admin(req)

    # Delete events first, then the session
    await db.session_replay_events.delete_many({"session_id": session_id})
    result = await db.session_recordings.delete_one({"session_id": session_id})

    if result.deleted_count == 0:
        return {"ok": False, "error": "Session not found"}

    return {"ok": True, "deleted": session_id}
