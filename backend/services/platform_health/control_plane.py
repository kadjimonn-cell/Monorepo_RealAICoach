"""
Control Plane Assembly Service — extracted from platform_health.py (Refactor Pass B).
Handles enterprise control plane payload construction with timeout-safe data collection.
"""
import asyncio
from typing import Dict, Any

import logging

logger = logging.getLogger("services.control_plane")


async def safe_collect_with_timeout(coro, timeout_seconds: float, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an async coroutine with a timeout, returning fallback on timeout/error."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ({timeout_seconds}s) collecting data, using fallback")
        return fallback
    except Exception as e:
        logger.warning(f"Error collecting data: {e}, using fallback")
        return fallback


def derive_severity_band(score: int, issues: int) -> str:
    """Derive a severity band label from score and issue count."""
    if score >= 95 and issues == 0:
        return "healthy"
    elif score >= 80:
        return "warning"
    elif score >= 60:
        return "degraded"
    else:
        return "critical"


def provider_label(provider_key: str) -> str:
    """Map provider keys to human-readable labels."""
    labels = {
        "stripe": "Stripe",
        "paypal": "PayPal",
        "fedapay": "FedaPay",
        "mobile_money": "Mobile Money",
        "apple": "Apple IAP",
        "google": "Google Play",
    }
    return labels.get(provider_key, provider_key.replace("_", " ").title())
