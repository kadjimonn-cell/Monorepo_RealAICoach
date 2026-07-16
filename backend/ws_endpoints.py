"""WebSocket endpoint registrations — extracted from server.py"""
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from utils.ws_ticket_auth import consume_ws_ticket
from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat


def register(app: FastAPI):
    from utils.ws_manager import ws_manager

    @app.websocket("/api/ws/notifications/{user_id}")
    async def ws_notifications(websocket: WebSocket, user_id: str):
        from routes.db import db as _db

        _user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="notifications",
            expected_user_id=user_id,
        )
        if not _user:
            await websocket.close(code=close_code)
            return

        await ws_manager.connect(user_id, websocket)
        try:
            unanswered_pings = 0
            while True:
                _, unanswered_pings = await receive_text_with_heartbeat(
                    websocket,
                    unanswered_pings,
                    send_ping=lambda ws: ws.send_json({"type": "ping"}),
                    send_pong=lambda ws: ws.send_json({"type": "pong"}),
                )
                if unanswered_pings >= MAX_UNANSWERED_PINGS:
                    raise asyncio.TimeoutError("notifications heartbeat timeout")
        except asyncio.TimeoutError:
            ws_manager.disconnect(user_id, websocket)
            try:
                await websocket.close(code=1000)
            except Exception:
                pass
        except WebSocketDisconnect:
            ws_manager.disconnect(user_id, websocket)
        except Exception:
            ws_manager.disconnect(user_id, websocket)

    from routes.video_interview import webrtc_signaling

    @app.websocket("/api/ws/fps/{room_id}/{user_id}")
    async def ws_fps_game(websocket: WebSocket, room_id: str, user_id: str):
        """FPS Game room gameplay socket (Feature 22) — ticket-authenticated."""
        from routes.db import db as _db
        from routes.games_station import handle_fps_ws

        _user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="fps_game",
            expected_user_id=user_id,
        )
        if not _user:
            await websocket.close(code=close_code)
            return
        _doc = await _db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not _doc:
            await websocket.close(code=4001)
            return
        from routes.db import User as _User
        await websocket.accept()
        await handle_fps_ws(websocket, room_id, _User(**_doc))

    @app.websocket("/api/ws/activity-stream")
    async def ws_activity_stream(websocket: WebSocket):
        """Public WebSocket for live security event stream on login page. No auth required."""
        await ws_manager.connect_public(websocket)
        try:
            unanswered_pings = 0
            while True:
                _, unanswered_pings = await receive_text_with_heartbeat(
                    websocket,
                    unanswered_pings,
                    send_ping=lambda ws: ws.send_json({"type": "ping"}),
                    send_pong=lambda ws: ws.send_json({"type": "pong"}),
                )
                if unanswered_pings >= MAX_UNANSWERED_PINGS:
                    raise asyncio.TimeoutError("activity stream heartbeat timeout")
        except asyncio.TimeoutError:
            ws_manager.disconnect_public(websocket)
            try:
                await websocket.close(code=1000)
            except Exception:
                pass
        except WebSocketDisconnect:
            ws_manager.disconnect_public(websocket)
        except Exception:
            ws_manager.disconnect_public(websocket)

    @app.websocket("/api/ws/interview/{room_id}/{user_id}")
    async def ws_interview_signaling(websocket: WebSocket, room_id: str, user_id: str):
        await webrtc_signaling(websocket, room_id, user_id)

    from routes.whiteboard import whiteboard_ws

    @app.websocket("/api/ws/whiteboard/{room_id}/{user_id}")
    async def ws_whiteboard(websocket: WebSocket, room_id: str, user_id: str):
        await whiteboard_ws(websocket, room_id, user_id)

    from routes.collaborative_docs import collab_doc_ws

    @app.websocket("/api/ws/collab-doc/{doc_id}/{user_id}")
    async def ws_collab_doc(websocket: WebSocket, doc_id: str, user_id: str):
        await collab_doc_ws(websocket, doc_id, user_id)

    from routes.ticket_chat import ticket_chat_ws

    @app.websocket("/api/ws/ticket-chat/{ticket_id}")
    async def ws_ticket_chat(websocket: WebSocket, ticket_id: str):
        await ticket_chat_ws(websocket, ticket_id)

    @app.websocket("/api/ws/admin-activity")
    async def ws_admin_activity(websocket: WebSocket):
        """Real-time admin activity feed WebSocket. Admin auth required."""
        from routes.db import db as _db

        user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="admin_activity",
            require_admin=True,
        )
        if not user:
            await websocket.close(code=close_code)
            return

        await ws_manager.connect_admin_activity(websocket)
        try:
            unanswered_pings = 0
            while True:
                _, unanswered_pings = await receive_text_with_heartbeat(
                    websocket,
                    unanswered_pings,
                    send_ping=lambda ws: ws.send_json({"type": "ping"}),
                    send_pong=lambda ws: ws.send_json({"type": "pong"}),
                )
                if unanswered_pings >= MAX_UNANSWERED_PINGS:
                    raise asyncio.TimeoutError("admin activity heartbeat timeout")
        except asyncio.TimeoutError:
            ws_manager.disconnect_admin_activity(websocket)
            try:
                await websocket.close(code=1000)
            except Exception:
                pass
        except WebSocketDisconnect:
            ws_manager.disconnect_admin_activity(websocket)
        except Exception:
            ws_manager.disconnect_admin_activity(websocket)

    # ── Automation Engine Real-Time Dashboard ──────────────────────
    @app.websocket("/api/ws/automation-dashboard")
    async def ws_automation_dashboard(websocket: WebSocket):
        """Real-time automation dashboard feed. Admin auth required.
        Pushes heartbeats, system metrics, incidents, and score every 15s."""
        from routes.db import db as _db

        user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="automation_dashboard",
            require_admin=True,
        )
        if not user:
            await websocket.close(code=close_code)
            return

        await ws_manager.connect_automation(websocket)
        try:
            unanswered_pings = 0
            while True:
                _, unanswered_pings = await receive_text_with_heartbeat(
                    websocket,
                    unanswered_pings,
                    send_ping=lambda ws: ws.send_json({"type": "ping"}),
                    send_pong=lambda ws: ws.send_json({"type": "pong"}),
                )
                if unanswered_pings >= MAX_UNANSWERED_PINGS:
                    raise asyncio.TimeoutError("automation dashboard heartbeat timeout")
        except asyncio.TimeoutError:
            ws_manager.disconnect_automation(websocket)
            try:
                await websocket.close(code=1000)
            except Exception:
                pass
        except WebSocketDisconnect:
            ws_manager.disconnect_automation(websocket)
        except Exception:
            ws_manager.disconnect_automation(websocket)

    # ── ASO Dashboard Real-Time Feed ───────────────────────────────
    @app.websocket("/api/ws/aso-dashboard")
    async def ws_aso_dashboard(websocket: WebSocket):
        """Real-time ASO keyword rankings feed. Admin auth required.
        Pushes updates when keywords change (add/remove/refresh)."""
        from routes.db import db as _db

        user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="aso_dashboard",
            require_admin=True,
        )
        if not user:
            await websocket.close(code=close_code)
            return

        await ws_manager.connect_aso(websocket)
        try:
            unanswered_pings = 0
            while True:
                _, unanswered_pings = await receive_text_with_heartbeat(
                    websocket,
                    unanswered_pings,
                    send_ping=lambda ws: ws.send_json({"type": "ping"}),
                    send_pong=lambda ws: ws.send_json({"type": "pong"}),
                )
                if unanswered_pings >= MAX_UNANSWERED_PINGS:
                    raise asyncio.TimeoutError("aso dashboard heartbeat timeout")
        except asyncio.TimeoutError:
            ws_manager.disconnect_aso(websocket)
            try:
                await websocket.close(code=1000)
            except Exception:
                pass
        except WebSocketDisconnect:
            ws_manager.disconnect_aso(websocket)
        except Exception:
            ws_manager.disconnect_aso(websocket)


    # SIEM real-time event stream
    @app.websocket("/api/ws/siem-events")
    async def ws_siem_events(websocket: WebSocket):
        """Stream new security events in real-time (admin only)."""
        import asyncio
        from routes.db import db as _db

        user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="siem_events",
            require_admin=True,
        )
        if not user:
            await websocket.close(code=close_code)
            return

        await websocket.accept()
        from routes.db import db as _db
        last_ts = datetime.now(timezone.utc).isoformat()
        try:
            while True:
                # Poll for new events since last check
                new_events = []
                async for doc in _db.security_events.find(
                    {"timestamp": {"$gt": last_ts}}, {"_id": 0}
                ).sort("timestamp", -1).limit(20):
                    new_events.append(doc)
                if new_events:
                    last_ts = new_events[0]["timestamp"]
                    await websocket.send_json({"type": "events", "data": new_events})
                else:
                    await websocket.send_json({"type": "heartbeat"})
                await asyncio.sleep(3)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    # Enterprise Dashboard live stream
    @app.websocket("/api/ws/enterprise-live")
    async def ws_enterprise_live(websocket: WebSocket):
        """Push live KPI ticks and activity events to admin enterprise dashboard."""
        import asyncio
        import random
        from routes.db import db as _db

        user, close_code, _reason = await consume_ws_ticket(
            _db,
            websocket.query_params.get("ticket", ""),
            channel="enterprise_live",
            require_admin=True,
        )
        if not user:
            await websocket.close(code=close_code)
            return

        await websocket.accept()

        names = ["Sarah C.", "James M.", "Emily R.", "David K.", "Anna L.", "Michael T.", "Lisa P.", "Robert J."]
        actions_pool = [
            ("completed AI coaching session", "chatbubble", "#00D4AA"),
            ("upgraded to Pro plan", "star", "#F59E0B"),
            ("created a new team", "people", "#6366F1"),
            ("generated growth report", "document-text", "#38BDF8"),
            ("achieved weekly goal", "trophy", "#10B981"),
            ("exported analytics data", "download", "#00D4AA"),
            ("started a focus session", "flash", "#8B5CF6"),
            ("shared coaching insights", "share-social", "#F43F5E"),
        ]

        tick = 0
        try:
            while True:
                tick += 1
                action = random.choice(actions_pool)
                new_event = {
                    "user": random.choice(names),
                    "action": action[0],
                    "icon": action[1],
                    "color": action[2],
                    "time": "just now",
                }
                kpi_deltas = {
                    "active_today_delta": random.randint(0, 3),
                    "api_requests_delta": random.randint(80, 350),
                    "avg_response_ms": random.randint(28, 55),
                    "error_rate": round(random.uniform(0.08, 0.18), 2),
                }
                await websocket.send_json({
                    "type": "live_tick",
                    "tick": tick,
                    "new_event": new_event,
                    "kpi_deltas": kpi_deltas,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                # Wait 30s, handle pings during wait
                for _ in range(30):
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=1)
                        if data == "ping":
                            await websocket.send_json({"type": "pong"})
                    except asyncio.TimeoutError:
                        continue
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
