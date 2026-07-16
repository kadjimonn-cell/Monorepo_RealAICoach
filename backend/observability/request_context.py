from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any
from uuid import uuid4

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var: ContextVar[str] = ContextVar("span_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def _parse_traceparent(traceparent: str | None) -> tuple[str, str]:
    if not traceparent:
        return "", ""
    parts = str(traceparent).strip().split("-")
    if len(parts) < 4:
        return "", ""
    trace_id = parts[1].strip().lower()
    span_id = parts[2].strip().lower()
    if len(trace_id) != 32 or len(span_id) != 16:
        return "", ""
    return trace_id, span_id


def extract_request_observability_context(request: Any) -> dict[str, str]:
    headers = request.headers
    traceparent = headers.get("traceparent")
    trace_id, span_id = _parse_traceparent(traceparent)

    correlation_id = (
        headers.get("x-correlation-id")
        or (trace_id if trace_id else "")
        or f"corr_{uuid4().hex[:24]}"
    )

    session_id = headers.get("x-session-id") or headers.get("x-client-id") or ""

    return {
        "correlation_id": str(correlation_id),
        "trace_id": str(trace_id),
        "span_id": str(span_id),
        "session_id": str(session_id),
        "traceparent": str(traceparent or ""),
    }


def bind_request_context(ctx: dict[str, str], user_id: str = "") -> tuple[Token, Token, Token, Token, Token]:
    return (
        correlation_id_var.set(str(ctx.get("correlation_id") or "")),
        trace_id_var.set(str(ctx.get("trace_id") or "")),
        span_id_var.set(str(ctx.get("span_id") or "")),
        session_id_var.set(str(ctx.get("session_id") or "")),
        user_id_var.set(str(user_id or "")),
    )


def reset_request_context(tokens: tuple[Token, Token, Token, Token, Token]) -> None:
    correlation_id_var.reset(tokens[0])
    trace_id_var.reset(tokens[1])
    span_id_var.reset(tokens[2])
    session_id_var.reset(tokens[3])
    user_id_var.reset(tokens[4])


def get_context_snapshot() -> dict[str, str]:
    return {
        "correlation_id": correlation_id_var.get(),
        "trace_id": trace_id_var.get(),
        "span_id": span_id_var.get(),
        "session_id": session_id_var.get(),
        "user_id": user_id_var.get(),
    }
