"""Collaborative Whiteboard for Interview Rooms.

Real-time drawing sync via WebSocket, state persistence, export as snapshot.
"""

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from typing import Dict
import asyncio
import uuid
import json
import logging

from .db import db, require_auth
from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat

router = APIRouter(prefix="/whiteboard")
logger = logging.getLogger("routes.whiteboard")

# In-memory whiteboard rooms: room_id -> {participants: {user_id: WebSocket}, strokes: []}
_wb_rooms: Dict[str, Dict[str, any]] = {}


@router.get("/{room_id}")
async def get_whiteboard(room_id: str, request: Request):
    """Get saved whiteboard state for a room."""
    await require_auth(request)
    wb = await db.whiteboards.find_one({"room_id": room_id}, {"_id": 0})
    if not wb:
        return {"room_id": room_id, "strokes": [], "exists": False}
    return {**wb, "exists": True}


@router.post("/{room_id}/save")
async def save_whiteboard(room_id: str, request: Request):
    """Persist whiteboard state to database."""
    user = await require_auth(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    wb_data = {
        "room_id": room_id,
        "strokes": body.get("strokes", []),
        "updated_by": user.user_id,
        "updated_at": now,
    }

    existing = await db.whiteboards.find_one({"room_id": room_id})
    if existing:
        await db.whiteboards.update_one({"room_id": room_id}, {"$set": wb_data})
    else:
        wb_data["created_at"] = now
        wb_data["created_by"] = user.user_id
        await db.whiteboards.insert_one(wb_data)

    return {"success": True, "room_id": room_id}


@router.post("/{room_id}/clear")
async def clear_whiteboard(room_id: str, request: Request):
    """Clear all strokes from the whiteboard."""
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()

    await db.whiteboards.update_one(
        {"room_id": room_id},
        {"$set": {"strokes": [], "updated_by": user.user_id, "updated_at": now}},
    )

    # Broadcast clear to connected peers
    if room_id in _wb_rooms:
        msg = json.dumps({"type": "wb_clear", "user_id": user.user_id})
        for uid, ws in list(_wb_rooms[room_id].get("participants", {}).items()):
            if uid != user.user_id:
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    return {"success": True}


@router.get("/{room_id}/snapshots")
async def list_snapshots(room_id: str, request: Request):
    """List saved snapshots for a whiteboard room."""
    await require_auth(request)
    snapshots = await db.whiteboard_snapshots.find({"room_id": room_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return {"snapshots": snapshots}


@router.post("/{room_id}/snapshot")
async def save_snapshot(room_id: str, request: Request):
    """Save a named snapshot of the whiteboard."""
    user = await require_auth(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    snapshot = {
        "snapshot_id": f"snap_{uuid.uuid4().hex[:10]}",
        "room_id": room_id,
        "name": body.get("name", f"Snapshot {now[:16]}"),
        "strokes": body.get("strokes", []),
        "thumbnail_data": body.get("thumbnail_data", ""),
        "created_by": user.user_id,
        "created_at": now,
    }
    await db.whiteboard_snapshots.insert_one(snapshot)
    snapshot.pop("_id", None)

    return {"success": True, "snapshot": snapshot}


# WebSocket for real-time whiteboard collaboration
async def whiteboard_ws(ws: WebSocket, room_id: str, user_id: str):
    """WebSocket for real-time whiteboard drawing sync."""
    await ws.accept()

    if room_id not in _wb_rooms:
        _wb_rooms[room_id] = {"participants": {}}
    _wb_rooms[room_id]["participants"][user_id] = ws

    # Notify peers about new whiteboard participant
    join_msg = json.dumps({"type": "wb_peer_joined", "user_id": user_id})
    for uid, peer_ws in list(_wb_rooms[room_id]["participants"].items()):
        if uid != user_id:
            try:
                await peer_ws.send_text(join_msg)
            except Exception:
                pass

    try:
        unanswered_pings = 0
        while True:
            raw, unanswered_pings = await receive_text_with_heartbeat(ws, unanswered_pings)
            if unanswered_pings >= MAX_UNANSWERED_PINGS:
                raise asyncio.TimeoutError("whiteboard heartbeat timeout")
            if raw is None:
                continue

            # Forward drawing events to all other peers
            for uid, peer_ws in list(_wb_rooms[room_id]["participants"].items()):
                if uid != user_id:
                    try:
                        await peer_ws.send_text(raw)
                    except Exception:
                        pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Whiteboard WS error: {e}")
    finally:
        if room_id in _wb_rooms and user_id in _wb_rooms[room_id]["participants"]:
            del _wb_rooms[room_id]["participants"][user_id]
            leave_msg = json.dumps({"type": "wb_peer_left", "user_id": user_id})
            for uid, peer_ws in list(_wb_rooms[room_id].get("participants", {}).items()):
                try:
                    await peer_ws.send_text(leave_msg)
                except Exception:
                    pass
            if not _wb_rooms[room_id]["participants"]:
                del _wb_rooms[room_id]
