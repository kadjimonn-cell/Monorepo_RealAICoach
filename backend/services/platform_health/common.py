"""Reusable helpers for enterprise platform health workflows."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional


def derive_severity_band(score: int, issues: int) -> str:
    """Map latest audit score/issues to severity bands used by rollback policy."""
    if score < 70 or issues >= 10:
        return "critical"
    if score < 85 or issues >= 5:
        return "high"
    if score < 95 or issues > 0:
        return "medium"
    return "low"


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def provider_label(provider_key: str) -> str:
    labels = {
        "stripe": "Stripe",
        "paypal": "PayPal",
        "paypal_js": "PayPal JS",
        "fedapay": "FedaPay",
        "mobile_money_fedapay": "FedaPay",
        "iap_apple": "Apple IAP",
        "iap_google": "Google IAP",
    }
    return labels.get(provider_key, provider_key.replace("_", " ").title())


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def compute_ledger_entry_hash(
    *,
    sequence: int,
    prev_hash: str,
    event_type: str,
    transaction_id: str,
    provider: str,
    user_id: str,
    payload: Dict[str, Any],
    created_at: str,
) -> str:
    hash_input = json.dumps(
        {
            "sequence": sequence,
            "prev_hash": prev_hash,
            "event_type": event_type,
            "transaction_id": transaction_id,
            "provider": provider,
            "user_id": user_id,
            "payload": payload,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def parse_datetime_value(raw_value: Any) -> Optional[datetime]:
    """Best-effort datetime parser for ISO strings/datetime objects."""
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=timezone.utc)
        return raw_value.astimezone(timezone.utc)

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    return None


def percentile(values: List[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = max(0, min(len(sorted_values) - 1, int(round((percentile_value / 100.0) * (len(sorted_values) - 1)))))
    return float(sorted_values[rank])


def normalize_slo_auto_mitigation_policy(raw_policy: Optional[Dict[str, Any]], default_policy: Dict[str, Any]) -> Dict[str, Any]:
    source = raw_policy or {}
    normalized = {
        "enabled": bool(source.get("enabled", default_policy["enabled"])),
        "p95_latency_threshold_ms": int(max(120, min(5000, int(source.get("p95_latency_threshold_ms", default_policy["p95_latency_threshold_ms"]))))),
        "min_samples": int(max(10, min(2000, int(source.get("min_samples", default_policy["min_samples"]))))),
        "breach_consecutive_checks": int(max(1, min(12, int(source.get("breach_consecutive_checks", default_policy["breach_consecutive_checks"]))))),
        "cooldown_minutes": int(max(1, min(720, int(source.get("cooldown_minutes", default_policy["cooldown_minutes"]))))),
        "check_interval_seconds": int(max(30, min(3600, int(source.get("check_interval_seconds", default_policy["check_interval_seconds"]))))),
        "auto_fix_recipes": [
            str(item).strip() for item in (source.get("auto_fix_recipes") or default_policy["auto_fix_recipes"]) if str(item).strip()
        ],
    }
    if not normalized["auto_fix_recipes"]:
        normalized["auto_fix_recipes"] = list(default_policy["auto_fix_recipes"])
    return normalized
