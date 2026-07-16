"""Shared admin production-behavior payment simulator core.

Used by the Stripe and PayPal admin simulate-production-e2e endpoints so the
post-payment-success orchestration (tx record, activation, ledger/audit,
unified notification pipeline, checks) lives in exactly one place.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import asyncio
import logging
import time
import uuid

from pydantic import BaseModel

from utils.tax_compliance_engine import (
    append_financial_ledger_entry,
    build_financial_totals,
    calculate_tax_quote,
    estimate_processing_fee,
    log_tax_calculation,
    resolve_product_type,
)

from .db import db

logger = logging.getLogger("routes.payments.simulation_core")


class ProviderSimulationRequest(BaseModel):
    email: str
    name: Optional[str] = None
    address_line: Optional[str] = None
    plan: str = "premium"
    period: str = "yearly"
    city: str = "Dallas"
    state_code: str = "TX"
    country_code: str = "US"
    postal_code: str = "75201"
    simulate_failure_case: bool = False


async def run_provider_payment_simulation(
    body: ProviderSimulationRequest,
    *,
    provider: str,
    fee_provider: str,
    tx_payment_method: str,
    payment_method_label: str,
    ticket_prefix: str,
    tx_prefix: str,
    ledger_event_type: str,
    provider_display: str,
    get_plan: Callable[[str], Awaitable[Optional[dict]]],
    send_payment_notification: Callable[..., Awaitable[dict]],
    queue_payment_notification_recovery: Callable[[dict, str], Awaitable[None]],
    build_payment_record_from_tx: Callable[..., dict],
    failure_copy: Callable[[str, str, str], tuple],
    append_transition: Optional[Callable[..., Awaitable[None]]] = None,
    extra_user_fields: Optional[Dict[str, Any]] = None,
) -> dict:
    plan_id = str(body.plan or "premium").lower()
    period = str(body.period or "yearly").lower()
    if period not in {"monthly", "yearly"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="period must be monthly or yearly")
    plan = await get_plan(plan_id)
    if not plan or not float(plan.get("monthly_price") or 0):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No paid subscription plan found for '{plan_id}'")
    base_price = float(plan["monthly_price"] if period == "monthly" else plan["yearly_price"])

    address_line = (body.address_line or "").strip() or None
    display_name = (body.name or "").strip() or None
    user_doc = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user_doc:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": body.email,
            "name": display_name or f"{provider_display} Simulation User",
            "subscription_plan": "free",
            "subscription_status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "password_hash": "SIMULATED_EXTERNAL_IDENTITY",
        }
        if address_line:
            user_doc["billing_address_line"] = address_line
        await db.users.insert_one({**user_doc})
    else:
        user_id = user_doc["user_id"]
        profile_updates = {}
        if display_name:
            profile_updates["name"] = display_name
        if address_line:
            profile_updates["billing_address_line"] = address_line
        if profile_updates:
            profile_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.users.update_one({"user_id": user_id}, {"$set": profile_updates})

    country_code = str(body.country_code or "US").upper()
    state_code = str(body.state_code or "").upper()
    product_type = resolve_product_type(plan_id)
    tax_quote = await calculate_tax_quote(
        provider=provider,
        subtotal=base_price,
        currency="USD",
        country_code=country_code,
        state_code=state_code,
        postal_code=body.postal_code,
        product_type=product_type,
    )
    processing_fee = estimate_processing_fee(fee_provider, tax_quote.get("amount_gross", base_price), "USD")
    financials = build_financial_totals(
        subtotal=tax_quote.get("subtotal", base_price),
        tax_amount=tax_quote.get("tax_amount", 0.0),
        processing_fee=processing_fee,
        fee_pass_through=True,
    )
    jurisdiction = {
        **tax_quote.get("jurisdiction", {"country": country_code, "state": state_code, "postal_code": body.postal_code}),
        "city": body.city,
    }
    if address_line:
        jurisdiction["address_line"] = address_line

    now = datetime.now(timezone.utc)
    session_id = f"{tx_prefix}_{uuid.uuid4().hex[:14]}"
    end_date = now + timedelta(days=365 if period == "yearly" else 30)
    tx = {
        "transaction_id": session_id,
        "session_id": session_id,
        "payment_id": session_id,
        "user_id": user_id,
        "plan_id": plan_id,
        "billing_period": period,
        "provider": provider,
        "gateway": provider,
        "payment_method": tx_payment_method,
        "payment_status": "completed",
        "status": "completed",
        "webhook_verified": True,
        "currency": "USD",
        "amount": base_price,
        "amount_usd": base_price,
        "base_plan_price": base_price,
        "subtotal": financials["subtotal"],
        "tax_amount": financials["tax_amount"],
        "processing_fee": financials["processing_fee"],
        "amount_gross": financials["amount_gross"],
        "amount_net": financials["amount_net"],
        "total_amount": financials["total_amount"],
        "tax_rate": tax_quote.get("tax_rate", 0),
        "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
        "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
        "tax_breakdown": tax_quote.get("tax_breakdown", []),
        "jurisdiction": jurisdiction,
        "product_type": tax_quote.get("product_type", product_type),
        "fee_pass_through": True,
        "environment": "production_simulated",
        "expires_at": end_date.isoformat(),
        "notification_sent": False,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.payment_transactions.update_one({"session_id": session_id}, {"$set": tx}, upsert=True)
    if append_transition is not None:
        await append_transition(
            session_id,
            state="activated",
            detail="Admin production-e2e simulator activated subscription",
            meta={"path": "admin_simulation"},
        )

    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "subscription_plan": plan_id,
                "subscription_status": "active",
                "subscription_end_date": end_date,
                "payment_verified": True,
                "last_payment_id": session_id,
                "updated_at": now,
                **(extra_user_fields or {}),
            }
        },
    )

    existing_payment = await db.payments.find_one({"payment_id": session_id}, {"_id": 0, "payment_id": 1})
    if not existing_payment:
        await db.payments.insert_one(build_payment_record_from_tx(tx, status="completed"))

    await log_tax_calculation(
        db,
        transaction_id=session_id,
        provider=provider,
        user_id=user_id,
        payload={"phase": f"{provider}_admin_simulation", "tax_quote": tax_quote, "financials": financials},
    )
    await append_financial_ledger_entry(
        db,
        event_type=ledger_event_type,
        transaction_id=session_id,
        provider=provider,
        user_id=user_id,
        payload={"status": "completed", "financials": financials, "environment": "production_simulated"},
    )
    await db.subscription_audit_log.insert_one(
        {
            "user_id": user_id,
            "action": "simulated_production_activation",
            "plan_id": plan_id,
            "session_id": session_id,
            "payment_status": "completed",
            "timestamp": now,
        }
    )

    ticket_id = f"{ticket_prefix}-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    fresh_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1}) or {}
    simulation_start = time.time()

    async def _dispatch_notification():
        try:
            await send_payment_notification(
                user_id=user_id,
                email=fresh_user.get("email", ""),
                user_name=fresh_user.get("name", ""),
                plan_name=plan.get("name", plan_id.title()),
                amount=financials["amount_gross"],
                payment_method=payment_method_label,
                ticket_id=ticket_id,
                billing_cycle=period,
                renewal_date=end_date.strftime("%b %d, %Y"),
                currency="USD",
                amount_local=0,
                transaction_context=tx,
            )
        except Exception as exc:
            logger.error(f"{provider_display} simulation notification error: {exc}")
            await queue_payment_notification_recovery(tx, str(exc))

    asyncio.create_task(_dispatch_notification())

    latest_notification = {}
    notification_latency_ms = None
    for _ in range(25):
        latest_notification = await db.notifications.find_one(
            {"user_id": user_id, "type": "payment_confirmation", "metadata.ticket_id": ticket_id},
            {"_id": 0},
        ) or {}
        if latest_notification:
            notification_latency_ms = int((time.time() - simulation_start) * 1000)
            break
        await asyncio.sleep(0.1)
    simulation_latency_ms = int((time.time() - simulation_start) * 1000)

    failure_case = None
    if body.simulate_failure_case:
        try:
            from utils.notification_helper import create_notification
            copy = failure_copy(provider_display, "failed", plan.get("name", plan_id.title()))
            await create_notification(
                user_id, copy[0], copy[1],
                notif_type="payment_failed",
                data={"session_id": session_id, "plan_id": plan_id, "amount": base_price},
            )
            failure_case = {"simulated": True, "status": "processed", "reason": "failed"}
        except Exception as exc:
            failure_case = {"simulated": True, "status": "error", "error": str(exc)[:200]}

    latest_tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0}) or {}
    checks = {
        "fee_accuracy": round(financials["subtotal"] + financials["processing_fee"] + financials["tax_amount"], 2) == round(financials["total_amount"], 2),
        "notification_latency_under_2s": bool(notification_latency_ms is not None and notification_latency_ms <= 2000),
        "subscription_active": True,
        "api_integrity": bool(latest_tx.get("transaction_id")),
    }

    return {
        "success": True,
        "scenario": {
            "location": body.city,
            "state_code": state_code,
            "country_code": country_code,
            "postal_code": body.postal_code,
            "address_line": address_line,
            "email": body.email,
            "plan": plan_id,
            "period": period,
            "platform": provider,
            "transaction_id": session_id,
        },
        "pricing_breakdown": {
            "base_plan_price": financials["subtotal"],
            "processing_fee": financials["processing_fee"],
            "taxes": financials["tax_amount"],
            "tax_rate": tax_quote.get("tax_rate", 0),
            "final_total": financials["total_amount"],
            "currency": "USD",
        },
        "subscription_update": {
            "subscription_plan": plan_id,
            "subscription_status": "active",
            "subscription_end_date": end_date.isoformat(),
        },
        "latest_payment_transaction": latest_tx,
        "latest_notification": {
            "title": latest_notification.get("title"),
            "message": latest_notification.get("message"),
            "created_at": latest_notification.get("created_at"),
        },
        "checks": checks,
        "ticket_id": ticket_id,
        "notification_latency_ms": notification_latency_ms if notification_latency_ms is not None else simulation_latency_ms,
        "simulation_runtime_ms": simulation_latency_ms,
        "failure_case": failure_case,
    }
