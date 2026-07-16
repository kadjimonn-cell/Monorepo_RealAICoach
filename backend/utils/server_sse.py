"""Shared SSE response helper for server metrics routes."""

from __future__ import annotations

import json

from fastapi.responses import StreamingResponse

SSE_RETRY_MS = 5000


def sse_payload_response(payload: dict):
    def _iter():
        yield f"retry: {SSE_RETRY_MS}\n".encode("utf-8")
        yield b"event: snapshot\n"
        yield f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")

    return StreamingResponse(
        _iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )