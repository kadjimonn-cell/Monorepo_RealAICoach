"""GPS-backed payment plan catalog helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional
import re
from shared.pricing_policy import get_yearly_price_map, get_plan_amount

CANONICAL_PLAN_ORDER = ("free", "basic", "premium")

CANONICAL_YEARLY_PRICES: dict[str, float] = get_yearly_price_map()

DEFAULT_CANONICAL_PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "plan_id": "free",
        "id": "free",
        "name": "Free",
        "description": "Core access for getting started.",
        "monthly_price": 0.0,
        "yearly_price": 0.0,
        "features": [
            "Core AI access",
            "Basic dashboard",
            "Community support",
        ],
        "limitations": [
            "Limited daily usage",
            "No advanced automation",
        ],
        "daily_conversation_limit": 3,
        "scenario_access": ["beginner"],
        "analytics_access": False,
        "export_formats": ["txt"],
        "automation_enabled": False,
        "print_enabled": False,
        "history_days": 7,
        "status": "active",
        "currency": "USD",
        "badge": "free",
    },
    "basic": {
        "plan_id": "basic",
        "id": "basic",
        "name": "Basic",
        "description": "For growing users and teams.",
        "monthly_price": get_plan_amount("basic", "monthly"),
        "yearly_price": CANONICAL_YEARLY_PRICES["basic"],
        "features": [
            "Higher daily limits",
            "Standard analytics",
            "Priority queue",
        ],
        "limitations": [
            "No premium-only modules",
        ],
        "daily_conversation_limit": 80,
        "scenario_access": ["beginner", "intermediate"],
        "analytics_access": True,
        "export_formats": ["txt", "csv", "pdf"],
        "automation_enabled": True,
        "print_enabled": False,
        "history_days": 30,
        "status": "active",
        "currency": "USD",
        "badge": "basic",
    },
    "premium": {
        "plan_id": "premium",
        "id": "premium",
        "name": "Premium",
        "description": "Full platform access with advanced governance.",
        "monthly_price": get_plan_amount("premium", "monthly"),
        "yearly_price": CANONICAL_YEARLY_PRICES["premium"],
        "features": [
            "Unlimited daily usage",
            "Advanced analytics",
            "Automation and governance",
        ],
        "limitations": [],
        "daily_conversation_limit": -1,
        "scenario_access": ["beginner", "intermediate", "advanced"],
        "analytics_access": True,
        "export_formats": ["txt", "csv", "pdf", "docx", "png"],
        "automation_enabled": True,
        "print_enabled": True,
        "history_days": -1,
        "status": "active",
        "currency": "USD",
        "badge": "premium",
    },
}

def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _normalize_plan(raw: Dict[str, Any]) -> Dict[str, Any]:
    plan_id = str(raw.get("plan_id") or raw.get("id") or "").strip().lower()
    if not plan_id:
        return {}
    defaults = DEFAULT_CANONICAL_PLANS.get(plan_id, {})
    monthly_default = _safe_float(defaults.get("monthly_price", 0.0), 0.0)
    yearly_default = _safe_float(defaults.get("yearly_price", monthly_default * 12), monthly_default * 12)

    monthly = _safe_float(raw.get("monthly_price", raw.get("monthlyUSD", monthly_default)), monthly_default)
    yearly = _safe_float(raw.get("yearly_price", raw.get("yearlyUSD", yearly_default)), yearly_default)
    features = [str(item) for item in (raw.get("features") or defaults.get("features") or [])]
    limitations = [str(item) for item in (raw.get("limitations") or defaults.get("limitations") or [])]
    joined = " ".join([*features, *limitations]).lower()

    def _derive_daily_limit() -> int:
        explicit = raw.get("daily_conversation_limit")
        if explicit is not None:
            try:
                return int(explicit)
            except Exception:
                pass
        if "unlimited" in joined:
            return -1
        match = re.search(r"\b(\d+)\s+(?:ai\s+)?conversations?\s+per\s+day\b", joined)
        return int(match.group(1)) if match else 3

    def _derive_scenarios() -> list[str]:
        explicit = raw.get("scenario_access")
        if explicit:
            return list(explicit)
        feature_text = " ".join(features).lower()
        if "all scenarios" in feature_text and "advanced" in feature_text:
            return ["beginner", "intermediate", "advanced"]
        levels = []
        for level in ("beginner", "intermediate", "advanced"):
            if re.search(rf"\b{level}\b[^.]*\bscenarios?\b|\bscenarios?\b[^.]*\b{level}\b", feature_text):
                levels.append(level)
        return levels or ["beginner"]

    def _derive_export_formats() -> list[str]:
        explicit = raw.get("export_formats")
        if explicit:
            return list(explicit)
        if "all formats" in joined:
            return ["txt", "csv", "pdf", "docx", "png"]
        formats = sorted({item.lower() for group in re.findall(r"\(([^)]*)\)", " ".join(features)) for item in re.split(r"[,/\s]+", group) if item.lower() in {"txt", "csv", "pdf", "docx", "png"}})
        return formats

    daily_limit = _derive_daily_limit()
    export_formats = _derive_export_formats()
    normalized = {
        **raw,
        "id": plan_id,
        "plan_id": plan_id,
        "name": str(raw.get("name") or plan_id.title()),
        "description": str(raw.get("description") or ""),
        "monthly_price": monthly,
        "yearly_price": yearly,
        "badge": str(raw.get("badge") or plan_id),
        "features": features,
        "limitations": limitations,
        "daily_conversation_limit": int(raw.get("daily_conversation_limit", daily_limit if daily_limit is not None else defaults.get("daily_conversation_limit", 3))),
        "scenario_access": raw.get("scenario_access") or _derive_scenarios() or list(defaults.get("scenario_access") or ["beginner"]),
        "analytics_access": bool(raw.get("analytics_access", defaults.get("analytics_access", "analytics" in joined or plan_id != "free"))),
        "export_formats": export_formats or list(defaults.get("export_formats") or []),
        "automation_enabled": bool(raw.get("automation_enabled", defaults.get("automation_enabled", "automation" in joined and "no automation" not in joined))),
        "print_enabled": bool(raw.get("print_enabled", defaults.get("print_enabled", "print enabled" in joined or "print" in export_formats))),
        "history_days": int(raw.get("history_days", defaults.get("history_days", -1 if "unlimited history" in joined else (int(re.search(r"\b(\d+)\s*-?day", joined).group(1)) if re.search(r"\b(\d+)\s*-?day", joined) else 7)))),
        "status": str(raw.get("status") or "active"),
        "currency": str(raw.get("currency") or "USD").upper(),
    }
    return normalized


async def get_subscription_plans_from_gps(*, include_deprecated: bool = False) -> dict[str, dict[str, Any]]:
    from routes.global_platform_state import get_global_platform_state
    from routes.db import db

    state = await get_global_platform_state()
    records: list[dict[str, Any]] = list((state or {}).get("plans") or [])
    if not records:
        try:
            records = await db.subscription_plans.find({}, {"_id": 0}).to_list(200)
        except Exception:
            records = []

    plans: dict[str, dict[str, Any]] = {}
    for raw in records:
        item = _normalize_plan(raw)
        if not item:
            continue
        canonical_yearly = CANONICAL_YEARLY_PRICES.get(item["id"])
        if canonical_yearly is not None and canonical_yearly > 0:
            item["yearly_price"] = canonical_yearly
        if not include_deprecated and item.get("status") == "deprecated":
            continue
        plans[item["id"]] = item

    # Permanent canonical floor: ensure Free/Basic/Premium always exist.
    for plan_id in CANONICAL_PLAN_ORDER:
        if plan_id in plans:
            continue
        canonical = _normalize_plan(DEFAULT_CANONICAL_PLANS[plan_id])
        if canonical:
            plans[plan_id] = canonical

    ordered: dict[str, dict[str, Any]] = {}
    for plan_id in CANONICAL_PLAN_ORDER:
        if plan_id in plans:
            ordered[plan_id] = plans[plan_id]
    for plan_id in sorted([key for key in plans.keys() if key not in CANONICAL_PLAN_ORDER]):
        ordered[plan_id] = plans[plan_id]
    return ordered


async def get_subscription_plan_catalog(*, include_deprecated: bool = False) -> list[dict[str, Any]]:
    plans = await get_subscription_plans_from_gps(include_deprecated=include_deprecated)
    return list(plans.values())


async def get_subscription_plan_from_gps(plan_id: Optional[str], *, default_plan_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    plans = await get_subscription_plans_from_gps()
    key = str(plan_id or "").strip().lower()
    if key in plans:
        return deepcopy(plans[key])
    if default_plan_id and str(default_plan_id).lower() in plans:
        return deepcopy(plans[str(default_plan_id).lower()])
    return None


async def require_paid_subscription_plan(plan_id: Optional[str]) -> dict[str, Any]:
    from fastapi import HTTPException

    from utils.preprod_entitlement_lock import is_preprod_lock_active

    if is_preprod_lock_active():
        raise HTTPException(
            status_code=403,
            detail="Subscriptions are disabled until production launch.",
        )
    plan = await get_subscription_plan_from_gps(plan_id)
    if not plan or plan.get("id") == "free":
        raise HTTPException(status_code=400, detail="Invalid plan")
    return plan


async def get_plan_name(plan_id: Optional[str]) -> str:
    plan = await get_subscription_plan_from_gps(plan_id)
    if plan:
        return str(plan.get("name") or plan.get("id") or plan_id)
    return str(plan_id or "").title()