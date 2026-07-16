"""LLM Usage Logger — records every LLM call with model, token estimates, and cost.

Writes to `llm_usage_log` collection and powers the Admin LLM Billing Dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from routes.db import db

logger = logging.getLogger(__name__)


# ── Model pricing (USD per 1K tokens / per image for image models) ───────────
# Reflects published Emergent LLM key pricing as of 2026-02.
MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI text
    "gpt-4o":         {"input_per_1k": 0.0025, "output_per_1k": 0.0100, "kind": "text"},
    "gpt-4o-mini":    {"input_per_1k": 0.00015, "output_per_1k": 0.00060, "kind": "text"},
    "gpt-5.2":        {"input_per_1k": 0.0050, "output_per_1k": 0.0200, "kind": "text"},
    # Anthropic text
    "claude-sonnet-4.5":  {"input_per_1k": 0.0030, "output_per_1k": 0.0150, "kind": "text"},
    "claude-haiku-4.5":   {"input_per_1k": 0.0008, "output_per_1k": 0.0040, "kind": "text"},
    "claude-opus-4.5":    {"input_per_1k": 0.0150, "output_per_1k": 0.0750, "kind": "text"},
    # Google text
    "gemini-3-flash": {"input_per_1k": 0.00030, "output_per_1k": 0.00120, "kind": "text"},
    "gemini-3-pro":   {"input_per_1k": 0.00250, "output_per_1k": 0.01000, "kind": "text"},
    # Image gen
    "nano-banana":   {"per_image": 0.040, "kind": "image"},
    "gpt-image-1":   {"per_image": 0.040, "kind": "image"},
    # Whisper STT
    "whisper":       {"per_minute": 0.006, "kind": "audio"},
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def compute_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    images: int = 0,
    audio_minutes: float = 0.0,
) -> float:
    price = MODEL_PRICING.get(model)
    if not price:
        # Unknown model — fall back to gpt-4o pricing to avoid under-counting
        price = MODEL_PRICING["gpt-4o"]
    total = 0.0
    if price.get("kind") == "text":
        total += (input_tokens / 1000.0) * price.get("input_per_1k", 0)
        total += (output_tokens / 1000.0) * price.get("output_per_1k", 0)
    if price.get("kind") == "image":
        total += images * price.get("per_image", 0)
    if price.get("kind") == "audio":
        total += audio_minutes * price.get("per_minute", 0)
    return round(total, 6)


async def log_llm_call(
    *,
    model: str,
    provider: str = "openai",
    feature: str = "unknown",
    user_id: str | None = None,
    session_id: str | None = None,
    prompt_text: str = "",
    response_text: str = "",
    latency_ms: int | None = None,
    success: bool = True,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Persist one LLM call to the `llm_usage_log` collection (fire-and-forget safe)."""
    try:
        input_tokens = estimate_tokens(prompt_text)
        output_tokens = estimate_tokens(response_text)
        cost_usd = compute_cost_usd(model, input_tokens=input_tokens, output_tokens=output_tokens)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "provider": provider,
            "feature": feature,
            "user_id": user_id or "anonymous",
            "session_id": session_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "success": bool(success),
            "error": error,
        }
        if extra:
            entry.update(extra)
        await db.llm_usage_log.insert_one(entry)
    except Exception as e:  # pragma: no cover — never block the caller on logging
        logger.debug(f"llm_usage_logger: failed to log LLM call: {e}")
