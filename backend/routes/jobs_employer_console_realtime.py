"""Employer pipeline live sync via WebSocket."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .db import db
from utils.ws_ticket_auth import consume_ws_ticket

router = APIRouter(prefix="/ws/jobs/employer")
logger = logging.getLogger("routes.jobs.realtime")


class EmployerPipelineRealtimeManager:
    def __init__(self):
        self.rooms: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, room_id: str, connection_id: str, websocket: WebSocket) -> int:
        await websocket.accept()
        self.rooms[room_id][connection_id] = websocket
        return len(self.rooms[room_id])

    def disconnect(self, room_id: str, connection_id: str) -> int:
        room = self.rooms.get(room_id) or {}
        room.pop(connection_id, None)
        if not room and room_id in self.rooms:
            self.rooms.pop(room_id, None)
            return 0
        return len(room)

    async def broadcast(self, room_id: str, payload: Dict[str, Any], exclude_connection_id: str | None = None) -> None:
        room = dict(self.rooms.get(room_id) or {})
        dead: list[str] = []
        for connection_id, websocket in room.items():
            if exclude_connection_id and connection_id == exclude_connection_id:
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(connection_id)
        for connection_id in dead:
            self.disconnect(room_id, connection_id)


pipeline_realtime_manager = EmployerPipelineRealtimeManager()


async def _authenticate_employer_websocket(websocket: WebSocket) -> Dict[str, Any] | None:
    ticket = str(websocket.query_params.get("ticket") or "").strip()
    if not ticket:
        return None

    user, _close_code, _reason = await consume_ws_ticket(
        db,
        ticket,
        channel="jobs_employer_pipeline",
    )
    if not user:
        return None

    employer_app = await db.employer_applications.find_one(
        {"user_id": user.get("user_id"), "status": "approved"},
        {"_id": 0, "permissions": 1},
    )
    if not employer_app or "post_job" not in (employer_app.get("permissions") or []):
        return None
    return user


async def broadcast_employer_pipeline_event(employer_user_id: str, payload: Dict[str, Any]) -> None:
    if not employer_user_id:
        return
    await pipeline_realtime_manager.broadcast(employer_user_id, {"type": "pipeline_event", **payload})


@router.websocket("/pipeline")
async def employer_pipeline_websocket(websocket: WebSocket):
    user = await _authenticate_employer_websocket(websocket)
    if not user:
        await websocket.close(code=4401)
        return

    employer_user_id = str(user.get("user_id") or "")
    connection_id = f"pipews_{uuid.uuid4().hex[:10]}"
    member_count = await pipeline_realtime_manager.connect(employer_user_id, connection_id, websocket)
    await pipeline_realtime_manager.broadcast(
        employer_user_id,
        {
            "type": "pipeline_presence",
            "event_type": "pipeline_sync_connected",
            "connection_id": connection_id,
            "actor_user_id": employer_user_id,
            "actor_name": user.get("name") or "Recruiter",
            "members": member_count,
        },
    )

    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong", "connection_id": connection_id})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Employer pipeline websocket error: %s", exc)
    finally:
        remaining = pipeline_realtime_manager.disconnect(employer_user_id, connection_id)
        await pipeline_realtime_manager.broadcast(
            employer_user_id,
            {
                "type": "pipeline_presence",
                "event_type": "pipeline_sync_disconnected",
                "connection_id": connection_id,
                "actor_user_id": employer_user_id,
                "actor_name": user.get("name") or "Recruiter",
                "members": remaining,
            },
        )