"""
SLO Auto-Mitigation Service — extracted from platform_health.py (Refactor Pass B).
Handles SLO breach detection, mitigation cycle execution, and state persistence.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from routes.db import db

import logging

logger = logging.getLogger("services.slo_mitigation")

SLO_POLICY_KEY = "slo_auto_mitigation_policy"
SLO_STATE_KEY = "slo_auto_mitigation_state"


def normalize_slo_policy(raw_policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize and validate an SLO auto-mitigation policy document."""
    if not raw_policy:
        return {
            "enabled": False,
            "p95_threshold_ms": 300,
            "breach_streak_threshold": 3,
            "cooldown_minutes": 5,
        }
    return {
        "enabled": bool(raw_policy.get("enabled", False)),
        "p95_threshold_ms": int(raw_policy.get("p95_threshold_ms", 300)),
        "breach_streak_threshold": int(raw_policy.get("breach_streak_threshold", 3)),
        "cooldown_minutes": int(raw_policy.get("cooldown_minutes", 5)),
    }


async def get_slo_policy() -> Dict[str, Any]:
    """Get the current SLO auto-mitigation policy."""
    doc = await db.admin_settings.find_one({"key": SLO_POLICY_KEY}, {"_id": 0})
    return normalize_slo_policy(doc)


async def save_slo_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Save the SLO auto-mitigation policy."""
    normalized = normalize_slo_policy(policy)
    await db.admin_settings.update_one(
        {"key": SLO_POLICY_KEY},
        {"$set": {**normalized, "key": SLO_POLICY_KEY, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return normalized


async def get_slo_state() -> Dict[str, Any]:
    """Get the current SLO auto-mitigation runtime state."""
    doc = await db.admin_settings.find_one({"key": SLO_STATE_KEY}, {"_id": 0})
    if not doc:
        return {
            "breach_streak": 0,
            "last_check_at": None,
            "last_result": None,
            "last_mitigation_at": None,
            "total_mitigations": 0,
            "total_checks": 0,
        }
    return doc


async def save_slo_state(state: Dict[str, Any]):
    """Persist the SLO auto-mitigation runtime state."""
    await db.admin_settings.update_one(
        {"key": SLO_STATE_KEY},
        {"$set": {**state, "key": SLO_STATE_KEY}},
        upsert=True,
    )


def safe_float(raw_value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def percentile(values: List[float], pct: float) -> float:
    """Compute a percentile from a sorted list of values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)
