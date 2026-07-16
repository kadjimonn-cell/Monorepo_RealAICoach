from __future__ import annotations

import uuid
from typing import Any, Dict, List


async def build_payment_plan_drift_report(db: Any, state: Dict[str, Any], now_iso) -> Dict[str, Any]:
    plans = [p for p in (state.get("plans") or []) if p.get("status") != "deprecated"]
    missing_fields: List[Dict[str, Any]] = []
    for plan in plans:
        plan_id = plan.get("plan_id")
        for field in ("monthly_price", "yearly_price", "features"):
            if plan.get(field) in (None, "", []):
                missing_fields.append({"plan_id": plan_id, "field": field})

    recent_transactions = await db.payment_transactions.find(
        {},
        {"_id": 0, "plan_id": 1, "billing_period": 1, "payment_method": 1, "amount": 1, "base_amount_usd": 1, "created_at": 1},
    ).sort("created_at", -1).limit(50).to_list(50)

    plan_map = {str(p.get("plan_id")): p for p in plans}
    tx_mismatches: List[Dict[str, Any]] = []
    amount_variance_samples: List[Dict[str, Any]] = []

    for tx in recent_transactions:
        plan = plan_map.get(str(tx.get("plan_id") or ""))
        if not plan:
            tx_mismatches.append({"reason": "transaction_plan_missing_from_gps", "transaction": tx})
            continue
        period = str(tx.get("billing_period") or "monthly")
        expected = float(plan.get("yearly_price") if period == "yearly" else plan.get("monthly_price") or 0)
        observed = tx.get("base_amount_usd", tx.get("amount"))
        try:
            observed_f = float(observed or 0)
        except Exception:
            observed_f = 0.0
        if expected > 0 and observed_f > 0 and abs(expected - observed_f) > 0.01:
            amount_variance_samples.append(
                {
                    "reason": "historical_transaction_amount_variance",
                    "plan_id": tx.get("plan_id"),
                    "billing_period": period,
                    "expected": expected,
                    "observed": observed_f,
                    "payment_method": tx.get("payment_method"),
                    "note": "Informational only; historical provider totals can include taxes, fees, currency conversion, or legacy prices.",
                }
            )

    provider_methods = sorted({str(tx.get("payment_method") or "unknown") for tx in recent_transactions if tx.get("payment_method")})
    healthy = not missing_fields and not tx_mismatches and len(plans) > 0
    report = {
        "status": "healthy" if healthy else "attention",
        "gps_version": state.get("version"),
        "plan_count": len(plans),
        "missing_fields": missing_fields,
        "recent_transaction_count": len(recent_transactions),
        "provider_methods_seen": provider_methods,
        "transaction_mismatches": tx_mismatches[:20],
        "amount_variance_samples": amount_variance_samples[:20],
        "checked_at": now_iso(),
    }
    await db.gps_payment_plan_monitor_snapshots.insert_one({**report, "snapshot_id": f"gps_paymon_{uuid.uuid4().hex[:12]}"})
    return report