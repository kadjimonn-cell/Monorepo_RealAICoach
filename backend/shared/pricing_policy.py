from __future__ import annotations

GLOBAL_PRICING_POLICY = {
    "currency": "USD",
    "yearly_discount_pct": 20,
    "plans": {
        "free": {"id": "free", "name": "Free", "monthly": 0.0, "yearly": 0.0},
        "basic": {"id": "basic", "name": "Basic", "monthly": 5.99, "yearly": 57.50},
        "premium": {"id": "premium", "name": "Premium", "monthly": 15.99, "yearly": 153.50},
    },
}


def get_plan_amount(plan_id: str, billing_period: str = "monthly") -> float:
    normalized_plan = str(plan_id or "").strip().lower()
    normalized_period = str(billing_period or "monthly").strip().lower()
    plan = GLOBAL_PRICING_POLICY["plans"].get(normalized_plan) or GLOBAL_PRICING_POLICY["plans"]["basic"]
    if normalized_period == "yearly":
        return float(plan["yearly"])
    return float(plan["monthly"])


def get_yearly_discount_pct() -> int:
    return int(GLOBAL_PRICING_POLICY["yearly_discount_pct"])


def get_plan_name(plan_id: str) -> str:
    normalized_plan = str(plan_id or "").strip().lower()
    plan = GLOBAL_PRICING_POLICY["plans"].get(normalized_plan) or GLOBAL_PRICING_POLICY["plans"]["basic"]
    return str(plan["name"])


def get_monthly_price_label(plan_id: str) -> str:
    return f"${get_plan_amount(plan_id, 'monthly'):.2f}/mo"


def get_yearly_price_map() -> dict[str, float]:
    return {plan_id: float(plan["yearly"]) for plan_id, plan in GLOBAL_PRICING_POLICY["plans"].items()}


def get_monthly_price_map() -> dict[str, float]:
    return {plan_id: float(plan["monthly"]) for plan_id, plan in GLOBAL_PRICING_POLICY["plans"].items()}