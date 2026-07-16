"""Real-time ticket chat via WebSocket.

Rooms: one per ticket_id.  Both admin and end-user join the same room.
Messages are persisted to `support_submissions.reply_logs` so the
conversation is available even when no WS is connected.
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
from datetime import datetime, timezone
import asyncio
import json
import logging
from utils.ws_ticket_auth import consume_ws_ticket
from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat

logger = logging.getLogger("routes.ticket_chat")

# ── In-memory room state ──
# ticket_id -> list of (user_id, role, name, ws)
_rooms: Dict[str, List[dict]] = {}
# ticket_id -> set of user_ids currently typing
_typing: Dict[str, Set[str]] = {}


def _room_presence(ticket_id: str) -> list:
    """Return list of users currently in the room."""
    members = _rooms.get(ticket_id, [])
    return [{"user_id": m["user_id"], "name": m["name"], "role": m["role"]} for m in members]


async def _broadcast(ticket_id: str, payload: dict, exclude_ws: WebSocket = None):
    """Send JSON to every connection in a room."""
    dead = []
    for m in _rooms.get(ticket_id, []):
        if m["ws"] is exclude_ws:
            continue
        try:
            await m["ws"].send_json(payload)
        except Exception:
            dead.append(m)
    for m in dead:
        _rooms[ticket_id] = [x for x in _rooms.get(ticket_id, []) if x is not m]


async def ticket_chat_ws(ws: WebSocket, ticket_id: str):
    """WebSocket handler for ticket real-time chat."""
    from routes.db import db

    # ── Auth ──
    user_doc, close_code, _reason = await consume_ws_ticket(
        db,
        ws.query_params.get("ticket", ""),
        channel="ticket_chat",
    )
    if not user_doc:
        await ws.close(code=close_code)
        return

    user_id = str(user_doc.get("user_id") or "").strip()
    if not user_id:
        await ws.close(code=4001)
        return
    user_role = "admin" if bool(user_doc.get("is_admin")) else "user"
    user_name = user_doc.get("name") or user_doc.get("email") or "User"

    # Verify ticket exists
    ticket = await db.support_submissions.find_one(
        {"submission_id": ticket_id}, {"_id": 0, "submission_id": 1, "user_id": 1}
    )
    if not ticket:
        await ws.close(code=4004)
        return

    # Non-admin can only join their own ticket
    if user_role != "admin" and ticket.get("user_id") != user_id:
        await ws.close(code=4003)
        return

    await ws.accept()

    # ── Join room ──
    if ticket_id not in _rooms:
        _rooms[ticket_id] = []
    member = {"user_id": user_id, "role": user_role, "name": user_name, "ws": ws}
    _rooms[ticket_id].append(member)

    logger.info(f"Ticket chat: {user_name} ({user_role}) joined room {ticket_id}")

    # Notify room of new presence
    await _broadcast(
        ticket_id,
        {
            "type": "presence",
            "action": "joined",
            "user_id": user_id,
            "name": user_name,
            "role": user_role,
            "members": _room_presence(ticket_id),
        },
    )

    try:
        unanswered_pings = 0
        while True:
            raw, unanswered_pings = await receive_text_with_heartbeat(
                ws,
                unanswered_pings,
                send_ping=lambda socket: socket.send_json({"type": "ping"}),
                send_pong=lambda socket: socket.send_json({"type": "pong"}),
            )
            if unanswered_pings >= MAX_UNANSWERED_PINGS:
                raise asyncio.TimeoutError("ticket chat heartbeat timeout")
            if raw is None:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            # ── Ping ──
            if msg_type == "ping":
                await ws.send_json({"type": "pong"})

            # ── Typing indicator ──
            elif msg_type == "typing":
                is_typing = data.get("is_typing", False)
                if ticket_id not in _typing:
                    _typing[ticket_id] = set()
                if is_typing:
                    _typing[ticket_id].add(user_id)
                else:
                    _typing[ticket_id].discard(user_id)
                await _broadcast(
                    ticket_id,
                    {
                        "type": "typing",
                        "user_id": user_id,
                        "name": user_name,
                        "role": user_role,
                        "is_typing": is_typing,
                    },
                    exclude_ws=ws,
                )

            # ── Chat message ──
            elif msg_type == "message":
                message_text = data.get("message", "").strip()
                if not message_text:
                    continue

                now_iso = datetime.now(timezone.utc).isoformat()

                # Persist to DB
                reply_entry = {
                    "from": user_id,
                    "from_name": user_name,
                    "role": user_role,
                    "message": message_text,
                    "at": now_iso,
                    "via": "realtime",
                }
                history_entry = {
                    "action": "admin_reply" if user_role == "admin" else "user_reply",
                    "note": message_text[:100],
                    "by": user_id,
                    "by_name": user_name,
                    "at": now_iso,
                }

                update_fields: dict = {"updated_at": now_iso}
                if user_role == "admin":
                    update_fields["status"] = "in_progress"
                    update_fields["last_admin_reply_at"] = now_iso

                await db.support_submissions.update_one(
                    {"submission_id": ticket_id},
                    {
                        "$push": {
                            "reply_logs": reply_entry,
                            "history": history_entry,
                        },
                        "$set": update_fields,
                    },
                )

                # Clear typing
                if ticket_id in _typing:
                    _typing[ticket_id].discard(user_id)

                # Broadcast message to room
                await _broadcast(
                    ticket_id,
                    {
                        "type": "message",
                        "from": user_id,
                        "from_name": user_name,
                        "role": user_role,
                        "message": message_text,
                        "at": now_iso,
                        "via": "realtime",
                    },
                )

                # De-escalate if admin replied
                if user_role == "admin":
                    try:
                        from routes.escalation_engine import de_escalate_ticket

                        await de_escalate_ticket(ticket_id, user_name)
                    except Exception:
                        pass

                # Push notification + email when admin replies
                if user_role == "admin":
                    ticket_owner = ticket.get("user_id", "")
                    tnum = ""
                    try:
                        t_doc = await db.support_submissions.find_one(
                            {"submission_id": ticket_id},
                            {"_id": 0, "ticket_number": 1, "subject": 1},
                        )
                        tnum = t_doc.get("ticket_number", ticket_id[:8]) if t_doc else ticket_id[:8]
                        subject_line = t_doc.get("subject", "Support Request") if t_doc else "Support Request"
                    except Exception:
                        tnum = ticket_id[:8]
                        subject_line = "Support Request"

                    # In-app notification
                    if ticket_owner:
                        try:
                            from routes.notification_engine import emit_notification
                            await emit_notification(
                                user_id=ticket_owner,
                                notif_type="ticket_admin_reply",
                                title=f"Reply on ticket {tnum}",
                                body=message_text[:100],
                                action_url="/my-tickets",
                                metadata={"ticket_number": tnum, "submission_id": ticket_id},
                            )
                        except Exception:
                            pass

                    # WS push to user not in room
                    try:
                        from utils.ws_manager import ws_manager
                        room_user_ids = {m["user_id"] for m in _rooms.get(ticket_id, [])}
                        if ticket_owner and ticket_owner not in room_user_ids:
                            await ws_manager.send_to_user(
                                ticket_owner,
                                {
                                    "type": "ticket_new_message",
                                    "ticket_id": ticket_id,
                                    "from_name": user_name,
                                    "message": message_text[:100],
                                },
                            )
                    except Exception:
                        pass

                    # Email notification to user
                    try:
                        import os as _os
                        from utils.email_service import render_email_logo
                        user_doc = await db.users.find_one({"user_id": ticket_owner}, {"_id": 0, "email": 1, "name": 1})
                        if user_doc and user_doc.get("email"):
                            recipient_email = str(user_doc.get("email") or "").strip()
                            recipient_name = str(user_doc.get("name") or "there").strip() or "there"
                            sender_name = str(user_name or "Support Team").strip() or "Support Team"
                            frontend_url = _os.environ.get("FRONTEND_BASE_URL", "")
                            reply_link = f"{frontend_url}/my-tickets" if frontend_url else ""
                            logo_html = render_email_logo(variant="support")
                            reply_cta = ""
                            if reply_link:
                                reply_cta = f'<div style="text-align:center;margin-top:24px;"><a href="{reply_link}" style="display:inline-block;padding:12px 32px;background:#3B82F6;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Reply to this message</a></div>'
                            f"""<div style="font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:32px 16px;background:#0B0F1A;">
                              <div style="border-radius:20px;overflow:hidden;border:1px solid #1E293B;">
                                <div style="background:linear-gradient(135deg,#0ea5e9,#6366f1);padding:36px 28px 28px;">
                                  {logo_html}
                                  <h2 style="color:#fff;font-size:20px;font-weight:800;margin:0 0 6px;">Support Reply</h2>
                                  <p style="color:rgba(255,255,255,0.82);font-size:13px;margin:0;">Ticket #{tnum} — {subject_line[:60]}</p>
                                </div>
                                <div style="background:#111827;padding:24px 28px;">
                                  <div style="background:#0F172A;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:16px;margin-bottom:20px;">
                                    <div style="white-space:pre-line;color:#CBD5E1;font-size:14px;line-height:1.7;">{message_text[:500]}</div>
                                  </div>
                                  {reply_cta}
                                </div>
                              </div>
                            </div>"""
                            from utils.email_service import send_catalog_template
                            await send_catalog_template(
                                recipient_email=recipient_email,
                                template_key="ticket_reply_agent",
                                user_name=recipient_name,
                                ticket_id=tnum,
                                ticket_subject=subject_line,
                                agent_name=sender_name,
                                reply_preview=message_text[:300],
                            )
                    except Exception as mail_err:
                        logger.warning(f"WS admin reply email failed: {mail_err}")

            # ── Read receipt ──
            elif msg_type == "read":
                await _broadcast(
                    ticket_id,
                    {
                        "type": "read",
                        "user_id": user_id,
                        "name": user_name,
                        "role": user_role,
                    },
                    exclude_ws=ws,
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Ticket chat error in room {ticket_id}: {e}")
    finally:
        # ── Leave room ──
        _rooms[ticket_id] = [m for m in _rooms.get(ticket_id, []) if m["ws"] is not ws]
        if ticket_id in _typing:
            _typing[ticket_id].discard(user_id)
        if not _rooms[ticket_id]:
            del _rooms[ticket_id]
            _typing.pop(ticket_id, None)
        else:
            await _broadcast(
                ticket_id,
                {
                    "type": "presence",
                    "action": "left",
                    "user_id": user_id,
                    "name": user_name,
                    "role": user_role,
                    "members": _room_presence(ticket_id),
                },
            )
        logger.info(f"Ticket chat: {user_name} left room {ticket_id}")
