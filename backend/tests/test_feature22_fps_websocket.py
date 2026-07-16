"""Feature 22 — FPS Game WebSocket contract tests (two-client kill flow).

Verifies:
- ws-ticket issued for channel='fps_game'
- Two simultaneous WS clients in same room
- {type:'joined'} initial payload from server on connect
- {type:'state'} relayed to other client
- 10 x {type:'hit'} => {type:'damage'} broadcasts + {type:'kill'} + {type:'respawn'} after ~3s
- Disconnect -> {type:'player_left'} to remaining client + match doc recorded (via /api/games-station/match-history)

Uses admin + free user credentials from /app/memory/test_credentials.md.

Run:  TEST_ADMIN_PASSWORD='NewAdminPass2026!' python -m pytest \
        backend/tests/test_feature22_fps_websocket.py -v -s
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
import requests
import websockets
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

ADMIN = {
    "email": "admin@realaicoach.app",
    "password": os.environ.get("TEST_ADMIN_PASSWORD", "NewAdminPass2026!"),
}
FREE_USER = {
    "email": "p1.free.1779113329@example.com",
    "password": "P1Free#2026!Aa",
}


def _login(creds: dict) -> tuple[str, str]:
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=creds,
        headers={"X-Client-Platform": "mobile"},
        timeout=30,
    )
    assert resp.status_code == 200, f"login failed for {creds['email']}: {resp.status_code} {resp.text[:200]}"
    body = resp.json()
    token = body.get("session_token") or body.get("token") or body.get("access_token")
    assert token, f"no token in login response for {creds['email']}"
    # Get user_id from /api/auth/me
    me = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert me.status_code == 200, f"/auth/me failed: {me.status_code} {me.text[:200]}"
    me_body = me.json()
    user_id = me_body.get("user_id") or me_body.get("id") or (me_body.get("user") or {}).get("user_id")
    assert user_id, f"no user_id in /auth/me: {me_body}"
    return token, user_id


def _ws_ticket(token: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/api/auth/ws-ticket",
        json={"channel": "fps_game"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert resp.status_code == 200, f"ws-ticket failed: {resp.status_code} {resp.text[:300]}"
    ticket = resp.json().get("ticket")
    assert ticket, f"no ticket in body: {resp.json()}"
    return ticket


def _join_room(token: str, room: str, name: str, model: str = "policeman") -> dict:
    resp = requests.post(
        f"{BASE_URL}/api/games-station/rooms/join",
        headers={"Authorization": f"Bearer {token}"},
        json={"room_name": room, "player_name": name, "model": model},
        timeout=15,
    )
    if resp.status_code == 429:
        pytest.skip(f"gameplay quota reached for token; body={resp.text[:200]}")
    assert resp.status_code == 200, f"join failed: {resp.status_code} {resp.text[:300]}"
    return resp.json()


async def _recv_until(ws, predicate, timeout: float = 6.0) -> dict | None:
    """Await messages until predicate(msg) is True or timeout."""
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            remaining = max(0.05, end - asyncio.get_event_loop().time())
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if predicate(msg):
            return msg
    return None


@pytest.fixture(scope="module")
def admin_session():
    tok, uid = _login(ADMIN)
    return {"token": tok, "user_id": uid}


@pytest.fixture(scope="module")
def free_session():
    tok, uid = _login(FREE_USER)
    return {"token": tok, "user_id": uid}


class TestFpsWebSocket:
    def test_ws_ticket_channel_fps_game(self, admin_session):
        ticket = _ws_ticket(admin_session["token"])
        assert isinstance(ticket, str) and len(ticket) > 8

    @pytest.mark.asyncio
    async def test_two_client_join_and_state_relay(self, admin_session, free_session):
        room = "pytest-ws-relay"
        _join_room(admin_session["token"], room, "AdminP", model="policeman")
        _join_room(free_session["token"], room, "FreeP", model="robotx")
        t1 = _ws_ticket(admin_session["token"])
        t2 = _ws_ticket(free_session["token"])
        u1 = admin_session["user_id"]
        u2 = free_session["user_id"]
        url1 = f"{WS_URL}/api/ws/fps/{room}/{u1}?ticket={t1}"
        url2 = f"{WS_URL}/api/ws/fps/{room}/{u2}?ticket={t2}"

        async with websockets.connect(url1, open_timeout=10) as ws1:
            joined1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=5))
            assert joined1["type"] == "joined"
            assert joined1["room_id"] == room
            assert joined1["self"]["user_id"] == u1

            async with websockets.connect(url2, open_timeout=10) as ws2:
                joined2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
                assert joined2["type"] == "joined"
                # ws1 should see player_joined event for ws2
                pj = await _recv_until(ws1, lambda m: m.get("type") == "player_joined", timeout=5)
                assert pj is not None, "ws1 did not receive player_joined"
                assert pj["player"]["user_id"] == u2

                # ws2 sends state, ws1 should receive relay
                await ws2.send(json.dumps({"type": "state", "pos": [1.0, 2.0, 3.0], "rot": [0.5, 0.1]}))
                relay = await _recv_until(ws1, lambda m: m.get("type") == "state" and m.get("user_id") == u2, timeout=5)
                assert relay is not None, "ws1 did not receive state relay"
                assert relay["pos"] == [1.0, 2.0, 3.0]

    @pytest.mark.asyncio
    async def test_kill_and_respawn_flow(self, admin_session, free_session):
        room = "pytest-ws-kill"
        _join_room(admin_session["token"], room, "Killer", model="policeman")
        _join_room(free_session["token"], room, "Victim", model="roboty")
        t1 = _ws_ticket(admin_session["token"])
        t2 = _ws_ticket(free_session["token"])
        u1 = admin_session["user_id"]
        u2 = free_session["user_id"]
        url1 = f"{WS_URL}/api/ws/fps/{room}/{u1}?ticket={t1}"
        url2 = f"{WS_URL}/api/ws/fps/{room}/{u2}?ticket={t2}"

        async with websockets.connect(url1, open_timeout=10) as ws1, \
                websockets.connect(url2, open_timeout=10) as ws2:
            # Drain joined + player_joined messages briefly
            await asyncio.wait_for(ws1.recv(), timeout=5)  # joined
            await asyncio.wait_for(ws2.recv(), timeout=5)  # joined
            # ws1 may also get player_joined for ws2; consume any pending
            await _recv_until(ws1, lambda m: m.get("type") == "player_joined", timeout=3)

            # ws1 hits ws2 ten times => 10 damages + kill
            damage_count = 0
            kill_msg = None
            for i in range(10):
                await ws1.send(json.dumps({"type": "hit", "target_id": u2}))
            # Collect messages on ws2
            end = asyncio.get_event_loop().time() + 6.0
            while asyncio.get_event_loop().time() < end:
                try:
                    remaining = max(0.05, end - asyncio.get_event_loop().time())
                    raw = await asyncio.wait_for(ws2.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                try:
                    m = json.loads(raw)
                except Exception:
                    continue
                if m.get("type") == "damage" and m.get("target_id") == u2:
                    damage_count += 1
                elif m.get("type") == "kill" and m.get("victim_id") == u2:
                    kill_msg = m
                    break
            assert damage_count >= 9, f"expected ~10 damage broadcasts on ws2, got {damage_count}"
            assert kill_msg is not None, "kill message not received by ws2"
            assert kill_msg["killer_id"] == u1

            # Wait for respawn (~3s later)
            respawn = await _recv_until(ws2, lambda m: m.get("type") == "respawn" and m.get("user_id") == u2, timeout=6.0)
            assert respawn is not None, "respawn message not received"
            assert respawn["hp"] == 100

    @pytest.mark.asyncio
    async def test_explicit_leave_finalizes_immediately_and_records_match(self, admin_session, free_session):
        """{type:'leave'} triggers immediate finalize (no 20s grace)."""
        room = "pytest-ws-leave-explicit"
        _join_room(admin_session["token"], room, "Stayer", model="policeman")
        _join_room(free_session["token"], room, "Leaver", model="robotx")
        t1 = _ws_ticket(admin_session["token"])
        t2 = _ws_ticket(free_session["token"])
        u1 = admin_session["user_id"]
        u2 = free_session["user_id"]
        url1 = f"{WS_URL}/api/ws/fps/{room}/{u1}?ticket={t1}"
        url2 = f"{WS_URL}/api/ws/fps/{room}/{u2}?ticket={t2}"

        async with websockets.connect(url1, open_timeout=10) as ws1:
            await asyncio.wait_for(ws1.recv(), timeout=5)  # joined
            ws2 = await websockets.connect(url2, open_timeout=10)
            try:
                await asyncio.wait_for(ws2.recv(), timeout=5)  # joined
                await _recv_until(ws1, lambda m: m.get("type") == "player_joined", timeout=3)
                # Send explicit leave — should finalize immediately (<3s)
                await ws2.send(json.dumps({"type": "leave"}))
            finally:
                # Give server a moment to process leave before closing
                await asyncio.sleep(0.3)
                await ws2.close()

            # player_left should arrive within ~3s (NOT wait full 20s grace)
            left = await _recv_until(
                ws1, lambda m: m.get("type") == "player_left" and m.get("user_id") == u2, timeout=5.0
            )
            assert left is not None, "player_left not received within 5s after explicit leave"

            await asyncio.sleep(0.8)  # match-record write

        history = requests.get(
            f"{BASE_URL}/api/games-station/match-history",
            headers={"Authorization": f"Bearer {free_session['token']}"},
            timeout=15,
        )
        assert history.status_code == 200
        matches = history.json().get("matches", [])
        assert any(m.get("room_id") == room for m in matches), \
            f"no match recorded for room {room}; got {[m.get('room_id') for m in matches[:5]]}"

    @pytest.mark.asyncio
    async def test_reconnect_within_grace_preserves_state(self, admin_session, free_session):
        """Disconnect + reconnect within 20s grace preserves kills/deaths on 'joined' (resumed=true)."""
        room = "pytest-ws-grace-resume"
        _join_room(admin_session["token"], room, "Killer2", model="policeman")
        _join_room(free_session["token"], room, "Victim2", model="roboty")
        t1 = _ws_ticket(admin_session["token"])
        t2 = _ws_ticket(free_session["token"])
        u1 = admin_session["user_id"]
        u2 = free_session["user_id"]
        url1_base = f"{WS_URL}/api/ws/fps/{room}/{u1}"
        url2 = f"{WS_URL}/api/ws/fps/{room}/{u2}?ticket={t2}"

        # First session for admin (killer): score 1 kill on victim
        async with websockets.connect(f"{url1_base}?ticket={t1}", open_timeout=10) as ws1, \
                websockets.connect(url2, open_timeout=10) as ws2:
            await asyncio.wait_for(ws1.recv(), timeout=5)  # joined
            await asyncio.wait_for(ws2.recv(), timeout=5)  # joined
            await _recv_until(ws1, lambda m: m.get("type") == "player_joined", timeout=3)
            # ws1 kills ws2 (10 hits)
            for _ in range(10):
                await ws1.send(json.dumps({"type": "hit", "target_id": u2}))
            kill = await _recv_until(ws1, lambda m: m.get("type") == "kill" and m.get("victim_id") == u2, timeout=6.0)
            assert kill is not None, "did not observe kill on ws1"
            assert kill["killer_kills"] == 1

        # Both disconnected (implicit — no explicit leave). Reconnect admin within grace.
        await asyncio.sleep(1.5)  # well under 20s grace
        t1b = _ws_ticket(admin_session["token"])
        async with websockets.connect(f"{url1_base}?ticket={t1b}", open_timeout=10) as ws1b:
            joined = json.loads(await asyncio.wait_for(ws1b.recv(), timeout=5))
            assert joined["type"] == "joined"
            assert joined.get("resumed") is True, f"expected resumed=true, got {joined}"
            assert joined["self"]["kills"] == 1, f"expected kills preserved=1, got {joined['self']}"
            # cleanly leave to not leak grace tasks
            await ws1b.send(json.dumps({"type": "leave"}))
            await asyncio.sleep(0.3)


    @pytest.mark.asyncio
    async def test_chat_message_broadcast(self, admin_session, free_session):
        """{type:'chat', text} is broadcast to all players including sender."""
        room = "pytest-ws-chat-broadcast"
        _join_room(admin_session["token"], room, "Chatter1", model="policeman")
        _join_room(free_session["token"], room, "Chatter2", model="robotx")
        t1 = _ws_ticket(admin_session["token"])
        t2 = _ws_ticket(free_session["token"])
        u1 = admin_session["user_id"]
        u2 = free_session["user_id"]
        url1 = f"{WS_URL}/api/ws/fps/{room}/{u1}?ticket={t1}"
        url2 = f"{WS_URL}/api/ws/fps/{room}/{u2}?ticket={t2}"
        async with websockets.connect(url1, open_timeout=10) as ws1, \
                websockets.connect(url2, open_timeout=10) as ws2:
            await asyncio.wait_for(ws1.recv(), timeout=5)
            await asyncio.wait_for(ws2.recv(), timeout=5)
            await _recv_until(ws1, lambda m: m.get("type") == "player_joined", timeout=3)
            # ws1 sends chat
            await ws1.send(json.dumps({"type": "chat", "text": "hello world"}))
            # ws2 should receive
            chat = await _recv_until(ws2, lambda m: m.get("type") == "chat", timeout=5.0)
            assert chat is not None, "chat not delivered to ws2"
            assert chat["user_id"] == u1
            assert chat["text"] == "hello world"
            assert chat["name"] == "Chatter1"
            # And sender also receives (broadcast includes self)
            self_chat = await _recv_until(ws1, lambda m: m.get("type") == "chat", timeout=5.0)
            assert self_chat is not None, "chat not echoed back to sender"

    @pytest.mark.asyncio
    async def test_killstreak_milestone_double_kill(self, admin_session, free_session):
        """Two consecutive kills without dying => streak=2 and milestone='double_kill'."""
        room = "pytest-ws-streak-double"
        _join_room(admin_session["token"], room, "Streaker", model="policeman")
        # Free user may be rate-limited by daily plan quota; skip gracefully
        try:
            _join_room(free_session["token"], room, "Prey", model="roboty")
        except AssertionError as exc:
            if "429" in str(exc) or "limit" in str(exc).lower():
                pytest.skip(f"free user daily gameplay limit reached: {exc}")
            raise
        t1 = _ws_ticket(admin_session["token"])
        t2 = _ws_ticket(free_session["token"])
        u1 = admin_session["user_id"]
        u2 = free_session["user_id"]
        url1 = f"{WS_URL}/api/ws/fps/{room}/{u1}?ticket={t1}"
        url2 = f"{WS_URL}/api/ws/fps/{room}/{u2}?ticket={t2}"
        async with websockets.connect(url1, open_timeout=10) as ws1, \
                websockets.connect(url2, open_timeout=10) as ws2:
            await asyncio.wait_for(ws1.recv(), timeout=5)
            await asyncio.wait_for(ws2.recv(), timeout=5)
            await _recv_until(ws1, lambda m: m.get("type") == "player_joined", timeout=3)

            # First kill
            for _ in range(10):
                await ws1.send(json.dumps({"type": "hit", "target_id": u2}))
            kill1 = await _recv_until(ws1, lambda m: m.get("type") == "kill" and m.get("victim_id") == u2, timeout=6.0)
            assert kill1 is not None
            assert kill1["streak"] == 1
            assert kill1.get("milestone") is None

            # Wait for respawn
            respawn = await _recv_until(ws1, lambda m: m.get("type") == "respawn" and m.get("user_id") == u2, timeout=6.0)
            assert respawn is not None, "respawn required to attempt 2nd kill"

            # Second kill => streak=2 => milestone double_kill
            for _ in range(10):
                await ws1.send(json.dumps({"type": "hit", "target_id": u2}))
            kill2 = await _recv_until(ws1, lambda m: m.get("type") == "kill" and m.get("victim_id") == u2, timeout=6.0)
            assert kill2 is not None, "second kill not observed"
            assert kill2["streak"] == 2, f"expected streak=2, got {kill2['streak']}"
            assert kill2.get("milestone") == "double_kill", f"expected milestone=double_kill, got {kill2.get('milestone')}"
