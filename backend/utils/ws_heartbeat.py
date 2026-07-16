"""Shared WebSocket heartbeat helpers for timeout-safe receive loops."""

import asyncio
import json
from typing import Awaitable, Callable, Optional, Tuple

from fastapi import WebSocket


RECEIVE_TIMEOUT_SECONDS = 60.0
PING_GRACE_TIMEOUT_SECONDS = 10.0
MAX_UNANSWERED_PINGS = 2


def _classify_payload(raw: str) -> str:
    lowered = str(raw).strip().lower()
    if lowered == "ping":
        return "ping"
    if lowered == "pong":
        return "pong"

    try:
        payload = json.loads(raw)
    except Exception:
        return "message"

    payload_type = str(payload.get("type", "")).strip().lower()
    if payload_type in {"ping", "pong"}:
        return payload_type
    return "message"


async def receive_text_with_heartbeat(
    websocket: WebSocket,
    unanswered_pings: int,
    *,
    receive_timeout: float = RECEIVE_TIMEOUT_SECONDS,
    ping_grace_timeout: float = PING_GRACE_TIMEOUT_SECONDS,
    max_unanswered_pings: int = MAX_UNANSWERED_PINGS,
    send_ping: Optional[Callable[[WebSocket], Awaitable[None]]] = None,
    send_pong: Optional[Callable[[WebSocket], Awaitable[None]]] = None,
) -> Tuple[Optional[str], int]:
    """
    Receive text with heartbeat timeout handling.

    Returns: (raw_message_or_none, unanswered_ping_count)
    - raw_message_or_none: None for heartbeat-only packets
    - unanswered_ping_count: incremented only when ping probe goes unanswered
    """

    ping_sender = send_ping or (lambda ws: ws.send_text("ping"))
    pong_sender = send_pong or (lambda ws: ws.send_text("pong"))

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=receive_timeout)
        kind = _classify_payload(raw)
        if kind == "ping":
            await pong_sender(websocket)
            return None, 0
        if kind == "pong":
            return None, 0
        return raw, 0
    except asyncio.TimeoutError:
        unanswered = unanswered_pings + 1

        try:
            await ping_sender(websocket)
        except Exception:
            return None, max_unanswered_pings

        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=ping_grace_timeout)
        except asyncio.TimeoutError:
            return None, unanswered

        kind = _classify_payload(raw)
        if kind == "ping":
            await pong_sender(websocket)
            return None, 0
        if kind == "pong":
            return None, 0
        return raw, 0
