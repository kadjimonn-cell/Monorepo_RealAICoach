"""WebRTC Video/Audio Interview Room — signaling + room management.

Endpoints:
- POST /interview-room/create       Create/get a room for an interview
- GET  /interview-room/{room_id}     Get room info
- POST /interview-room/{room_id}/join    Join room
- POST /interview-room/{room_id}/leave   Leave room
- POST /interview-room/{room_id}/end     End interview
- WebSocket /ws/interview/{room_id}/{user_id}  WebRTC signaling
"""

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from typing import Dict
import asyncio
import uuid
import json
import logging

from .db import db, require_auth
from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat

router = APIRouter(prefix="/interview-room")
logger = logging.getLogger("routes.video_interview")

# In-memory signaling rooms: room_id -> {participants: {user_id: WebSocket}}
_rooms: Dict[str, Dict[str, WebSocket]] = {}


def _iso_to_dt(value: str | None):
    try:
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _log_replay_event(
    room: dict,
    *,
    event_type: str,
    actor_id: str,
    actor_name: str,
    message: str,
    payload: dict | None = None,
):
    now = datetime.now(timezone.utc)
    started_at = _iso_to_dt(room.get("started_at"))
    second_offset = 0
    if started_at:
        second_offset = max(0, int((now - started_at).total_seconds()))
    event = {
        "event_id": f"rpe_{uuid.uuid4().hex[:12]}",
        "room_id": room.get("room_id"),
        "interview_id": room.get("interview_id"),
        "event_type": event_type,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "message": message,
        "second_offset": second_offset,
        "payload": payload or {},
        "created_at": now.isoformat(),
    }
    await db.interview_replay_events.insert_one({**event})


@router.post("/create")
async def create_room(request: Request):
    """Create or retrieve an interview room for a given interview."""
    user = await require_auth(request)
    body = await request.json()
    interview_id = body.get("interview_id", "")

    if not interview_id:
        raise HTTPException(status_code=400, detail="interview_id required")

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # Check authorization
    uid = user.user_id
    if uid not in [interview.get("employer_id"), interview.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not a participant of this interview")

    # Check if room already exists
    existing = await db.interview_rooms.find_one({"interview_id": interview_id}, {"_id": 0})
    if existing:
        if existing.get("status") == "ended":
            now = datetime.now(timezone.utc).isoformat()
            reset_fields = {
                "status": "waiting",
                "participants": [],
                "started_at": None,
                "ended_at": None,
                "duration_seconds": None,
                "chat_messages": [],
                "ai_suggestions": [],
                "reopened_at": now,
                "reopened_by": uid,
            }
            await db.interview_rooms.update_one({"room_id": existing["room_id"]}, {"$set": reset_fields})
            existing.update(reset_fields)
            await _log_replay_event(
                existing,
                event_type="room_reopened",
                actor_id=uid,
                actor_name=user.name,
                message="Interview room reopened for replay continuation.",
            )
        return {"room": existing}

    now = datetime.now(timezone.utc).isoformat()
    room_id = f"room_{uuid.uuid4().hex[:12]}"

    room = {
        "room_id": room_id,
        "interview_id": interview_id,
        "job_title": interview.get("job_title", ""),
        "employer_id": interview.get("employer_id", ""),
        "employer_name": interview.get("employer_name", ""),
        "candidate_id": interview.get("candidate_id", ""),
        "candidate_name": interview.get("candidate_name", ""),
        "interview_type": interview.get("interview_type", "video"),
        "status": "waiting",
        "participants": [],
        "started_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "chat_messages": [],
        "created_at": now,
    }

    await db.interview_rooms.insert_one({**room})
    await _log_replay_event(
        room,
        event_type="room_created",
        actor_id=uid,
        actor_name=user.name,
        message="Interview room created.",
    )
    return {"room": room}


@router.get("/{room_id}")
async def get_room(room_id: str, request: Request):
    """Get room details."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    uid = user.user_id
    if uid not in [room.get("employer_id"), room.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {"room": room}


@router.post("/{room_id}/join")
async def join_room(room_id: str, request: Request):
    """Join an interview room."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    uid = user.user_id
    if uid not in [room.get("employer_id"), room.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    if room.get("status") == "ended":
        raise HTTPException(status_code=400, detail="Interview has ended")

    now = datetime.now(timezone.utc).isoformat()
    participant = {
        "user_id": uid,
        "name": user.name,
        "role": "employer" if uid == room.get("employer_id") else "candidate",
        "joined_at": now,
    }

    participants = room.get("participants", [])
    if not any(p["user_id"] == uid for p in participants):
        participants.append(participant)

    update = {"participants": participants, "status": "active" if len(participants) >= 2 else "waiting"}
    if len(participants) >= 2 and not room.get("started_at"):
        update["started_at"] = now

    await db.interview_rooms.update_one({"room_id": room_id}, {"$set": update})

    # Update interview status
    await db.interview_bookings.update_one(
        {"interview_id": room["interview_id"]}, {"$set": {"status": "in_progress", "updated_at": now}}
    )

    await _log_replay_event(
        {**room, **update, "room_id": room_id},
        event_type="participant_joined",
        actor_id=uid,
        actor_name=user.name,
        message=f"{user.name} joined interview room.",
        payload={"role": participant.get("role")},
    )

    return {"success": True, "participant": participant, "status": update["status"]}


@router.post("/{room_id}/leave")
async def leave_room(room_id: str, request: Request):
    """Leave an interview room."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    participants = [p for p in room.get("participants", []) if p["user_id"] != user.user_id]
    status = "waiting" if participants else "ended"

    await db.interview_rooms.update_one(
        {"room_id": room_id}, {"$set": {"participants": participants, "status": status}}
    )

    await _log_replay_event(
        {**room, "participants": participants, "status": status},
        event_type="participant_left",
        actor_id=user.user_id,
        actor_name=user.name,
        message=f"{user.name} left interview room.",
        payload={"status": status},
    )

    return {"success": True, "status": status}


@router.post("/{room_id}/end")
async def end_room(room_id: str, request: Request):
    """End the interview room."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    uid = user.user_id
    if uid not in [room.get("employer_id"), room.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    now = datetime.now(timezone.utc).isoformat()
    duration = None
    if room.get("started_at"):
        start = datetime.fromisoformat(room["started_at"].replace("Z", "+00:00"))
        duration = int((datetime.now(timezone.utc) - start).total_seconds())

    await db.interview_rooms.update_one(
        {"room_id": room_id},
        {"$set": {"status": "ended", "ended_at": now, "duration_seconds": duration, "participants": []}},
    )

    await db.interview_bookings.update_one(
        {"interview_id": room["interview_id"]}, {"$set": {"status": "completed", "updated_at": now}}
    )

    await _log_replay_event(
        {**room, "status": "ended", "ended_at": now, "duration_seconds": duration},
        event_type="room_ended",
        actor_id=uid,
        actor_name=user.name,
        message="Interview room ended and finalized.",
        payload={"duration_seconds": duration or 0},
    )

    # Notify via WebSocket if connected
    if room_id in _rooms:
        for ws in list(_rooms[room_id].values()):
            try:
                await ws.send_json({"type": "room_ended", "ended_by": uid})
            except Exception:
                pass
        del _rooms[room_id]

    return {"success": True, "duration_seconds": duration}


@router.post("/{room_id}/chat")
async def send_chat(room_id: str, request: Request):
    """Send a chat message in the interview room."""
    user = await require_auth(request)
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message required")

    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    now = datetime.now(timezone.utc).isoformat()
    chat_msg = {
        "id": uuid.uuid4().hex[:8],
        "user_id": user.user_id,
        "name": user.name,
        "message": message,
        "sent_at": now,
    }

    await db.interview_rooms.update_one({"room_id": room_id}, {"$push": {"chat_messages": chat_msg}})

    await _log_replay_event(
        room,
        event_type="chat_message",
        actor_id=user.user_id,
        actor_name=user.name,
        message=f"Chat: {message[:120]}",
        payload={"message_id": chat_msg["id"]},
    )

    # Broadcast to connected WebSocket peers
    if room_id in _rooms:
        for uid, ws in list(_rooms[room_id].items()):
            if uid != user.user_id:
                try:
                    await ws.send_json({"type": "chat_message", "data": chat_msg})
                except Exception:
                    pass

    return {"success": True, "message": chat_msg}


@router.post("/{room_id}/ai-assist")
async def ai_interview_assist(room_id: str, request: Request):
    """AI assistant provides real-time interview help: questions, tips, evaluation."""
    await require_auth(request)
    body = await request.json()
    action = body.get("action", "suggest_question")
    context = body.get("context", "")

    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    interview = await db.interview_bookings.find_one(
        {"interview_id": room.get("interview_id")},
        {"_id": 0, "job_title": 1, "job_description": 1, "interview_type": 1, "position": 1},
    )
    job_ctx = ""
    if interview:
        job_ctx = f"Position: {interview.get('job_title') or interview.get('position', 'General')}"
        if interview.get("job_description"):
            job_ctx += f"\nJob Description: {interview['job_description'][:300]}"

    prompts = {
        "suggest_question": f"You are an expert interview AI assistant. Generate 3 relevant interview questions for this context:\n{job_ctx}\n{context}\nProvide concise, professional questions numbered 1-3.",
        "evaluate_response": f"You are an expert interview evaluator. Evaluate this candidate response:\n{context}\nProvide: (1) Strengths, (2) Areas for improvement, (3) Score 1-10. Keep each point to 1-2 sentences.",
        "coaching_tip": f"You are an expert interview coach. Provide a brief, actionable coaching tip for:\n{job_ctx}\n{context}\nKeep it under 3 sentences.",
        "summarize": f"You are an expert interview summarizer. Summarize this interview conversation:\n{context}\nProvide: Key topics discussed, candidate strengths, areas of concern, overall assessment. Keep it concise.",
    }

    prompt = prompts.get(action, prompts["suggest_question"])

    try:
        import os
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(api_key=EMERGENT_KEY, session_id=f"interview-ai-{room_id}-{uuid.uuid4().hex[:6]}").with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=prompt))

        # Save AI suggestion to room
        ai_msg = {
            "id": uuid.uuid4().hex[:8],
            "user_id": "ai_assistant",
            "name": "AI Interview Assistant",
            "message": response.strip(),
            "action": action,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "is_ai": True,
        }
        await db.interview_rooms.update_one({"room_id": room_id}, {"$push": {"ai_suggestions": ai_msg}})

        await _log_replay_event(
            room,
            event_type="ai_assist",
            actor_id="ai_assistant",
            actor_name="AI Interview Assistant",
            message=f"AI {action.replace('_', ' ')} response recorded.",
            payload={"action": action, "suggestion_id": ai_msg["id"]},
        )

        return {"success": True, "response": response.strip(), "action": action}
    except Exception as e:
        logger.error(f"AI interview assist error: {e}")
        raise HTTPException(status_code=500, detail="AI assistant unavailable")


@router.get("/{room_id}/replay-timeline")
async def get_replay_timeline(room_id: str, request: Request):
    """Get recording replay timeline with evaluator annotations for review boards."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    uid = user.user_id
    if uid not in [room.get("employer_id"), room.get("candidate_id")] and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    events = (
        await db.interview_replay_events.find({"room_id": room_id}, {"_id": 0})
        .sort("created_at", 1)
        .limit(600)
        .to_list(600)
    )
    annotations = (
        await db.interview_replay_annotations.find({"room_id": room_id}, {"_id": 0})
        .sort("created_at", 1)
        .limit(300)
        .to_list(300)
    )

    return {
        "room_id": room_id,
        "interview_id": room.get("interview_id"),
        "events": events,
        "annotations": annotations,
        "total_events": len(events),
        "total_annotations": len(annotations),
    }


@router.post("/{room_id}/replay-annotations")
async def add_replay_annotation(room_id: str, request: Request):
    """Add evaluator annotation to recording timeline (employer/admin)."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    uid = user.user_id
    can_annotate = user.is_admin or uid == room.get("employer_id")
    if not can_annotate:
        raise HTTPException(status_code=403, detail="Only evaluator roles can annotate replay timeline")

    body = await request.json()
    note = str(body.get("note") or "").strip()
    if len(note) < 3:
        raise HTTPException(status_code=400, detail="Annotation note must be at least 3 characters")

    second_offset = max(0, int(body.get("second_offset") or 0))
    category = str(body.get("category") or "general").strip().lower()[:40] or "general"
    severity = str(body.get("severity") or "low").strip().lower()
    if severity not in {"low", "medium", "high"}:
        severity = "low"
    tags_raw = body.get("tags") or []
    tags = [str(t).strip().lower()[:30] for t in tags_raw if str(t).strip()][:8]

    annotation = {
        "annotation_id": f"ann_{uuid.uuid4().hex[:12]}",
        "room_id": room_id,
        "interview_id": room.get("interview_id"),
        "second_offset": second_offset,
        "category": category,
        "severity": severity,
        "note": note,
        "tags": tags,
        "author_id": uid,
        "author_name": user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.interview_replay_annotations.insert_one({**annotation})
    await _log_replay_event(
        room,
        event_type="annotation_added",
        actor_id=uid,
        actor_name=user.name,
        message=f"Annotation added at T+{second_offset}s.",
        payload={"annotation_id": annotation["annotation_id"], "severity": severity, "category": category},
    )
    return {"success": True, "annotation": annotation}


@router.delete("/{room_id}/replay-annotations/{annotation_id}")
async def delete_replay_annotation(room_id: str, annotation_id: str, request: Request):
    """Delete evaluator annotation from replay timeline."""
    user = await require_auth(request)
    room = await db.interview_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    ann = await db.interview_replay_annotations.find_one(
        {"room_id": room_id, "annotation_id": annotation_id},
        {"_id": 0},
    )
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")

    can_delete = user.is_admin or user.user_id == room.get("employer_id") or user.user_id == ann.get("author_id")
    if not can_delete:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.interview_replay_annotations.delete_one({"room_id": room_id, "annotation_id": annotation_id})
    await _log_replay_event(
        room,
        event_type="annotation_deleted",
        actor_id=user.user_id,
        actor_name=user.name,
        message=f"Annotation removed ({annotation_id}).",
        payload={"annotation_id": annotation_id},
    )
    return {"success": True, "annotation_id": annotation_id}


# ═══════════════════════════════════════════════════════════════
# WebRTC SIGNALING via WebSocket
# ═══════════════════════════════════════════════════════════════


async def webrtc_signaling(ws: WebSocket, room_id: str, user_id: str):
    """WebSocket endpoint for WebRTC signaling (offer/answer/ICE)."""
    await ws.accept()

    if room_id not in _rooms:
        _rooms[room_id] = {}
    _rooms[room_id][user_id] = ws

    # Notify other peers about new participant
    for uid, peer_ws in list(_rooms[room_id].items()):
        if uid != user_id:
            try:
                await peer_ws.send_json({"type": "peer_joined", "user_id": user_id})
            except Exception:
                pass

    try:
        unanswered_pings = 0
        while True:
            raw, unanswered_pings = await receive_text_with_heartbeat(ws, unanswered_pings)
            if unanswered_pings >= MAX_UNANSWERED_PINGS:
                raise asyncio.TimeoutError("interview signaling heartbeat timeout")
            if raw is None:
                continue
            data = json.loads(raw)
            data.get("type", "")

            # Forward signaling messages to the target peer or all peers
            target = data.get("target")
            payload = {**data, "from": user_id}

            if target and target in _rooms.get(room_id, {}):
                try:
                    await _rooms[room_id][target].send_json(payload)
                except Exception:
                    pass
            else:
                # Broadcast to all other peers
                for uid, peer_ws in list(_rooms.get(room_id, {}).items()):
                    if uid != user_id:
                        try:
                            await peer_ws.send_json(payload)
                        except Exception:
                            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebRTC signaling error: {e}")
    finally:
        if room_id in _rooms and user_id in _rooms[room_id]:
            del _rooms[room_id][user_id]
            # Notify remaining peers
            for uid, peer_ws in list(_rooms.get(room_id, {}).items()):
                try:
                    await peer_ws.send_json({"type": "peer_left", "user_id": user_id})
                except Exception:
                    pass
            if not _rooms.get(room_id):
                del _rooms[room_id]


@router.websocket("/ws/{room_id}/{user_id}")
async def interview_room_websocket(ws: WebSocket, room_id: str, user_id: str):
    """Public signaling endpoint for interview room peers."""
    await webrtc_signaling(ws, room_id, user_id)
