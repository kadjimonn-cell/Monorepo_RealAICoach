from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from observability.request_context import get_context_snapshot

try:
    from opentelemetry import trace
except Exception:  # pragma: no cover
    trace = None


class JsonObservabilityFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_context_snapshot()
        trace_id = ctx.get("trace_id") or ""
        span_id = ctx.get("span_id") or ""

        if trace and (not trace_id or not span_id):
            try:
                current = trace.get_current_span()
                span_ctx = current.get_span_context() if current else None
                if span_ctx and span_ctx.is_valid:
                    if not trace_id:
                        trace_id = f"{span_ctx.trace_id:032x}"
                    if not span_id:
                        span_id = f"{span_ctx.span_id:016x}"
            except Exception:
                pass

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": ctx.get("correlation_id") or "",
            "trace_id": trace_id,
            "span_id": span_id,
            "session_id": ctx.get("session_id") or "",
            "user_id": ctx.get("user_id") or "",
            "module": record.module,
            "line": int(record.lineno or 0),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(service_name: str) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonObservabilityFormatter(service_name=service_name))
    root.addHandler(handler)
