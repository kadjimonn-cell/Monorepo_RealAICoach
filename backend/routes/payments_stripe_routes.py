"""Stripe checkout/status/webhook routes extracted from payments.py.

Shared subscription confirmation endpoints remain in payments.py; this module
owns Stripe route orchestration and provider-specific checkout/webhook handling.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import logging
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

from utils.email_service import is_email_configured
from utils.tax_compliance_engine import append_financial_ledger_entry, build_financial_totals, log_tax_calculation

from .db import db, get_current_user
from .payments_simulation_core import ProviderSimulationRequest, run_provider_payment_simulation
from .payments_catalog import get_subscription_plan_from_gps
from .payments_pricing_guard import safe_amount_value
from .subscription_enforcement import dispatch_subscription_expiry_notification


router = APIRouter()
logger = logging.getLogger("routes.payments.stripe_routes")
STRIPE_API_KEY = ""
STRIPE_WEBHOOK_SECRET = ""
ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "XOF", "XAF"}


def _build_provider_failure_copy(provider_label: str, state: str, plan_name: str) -> tuple[str, str]:
    provider = provider_label or "Payment Gateway"
    plan = plan_name or "subscription"
    normalized = str(state or "failed").strip().lower()
    if normalized in {"cancelled", "canceled"}:
        return ("Checkout cancelled", f"{provider} checkout was cancelled before payment completed. No charge was completed.")
    if normalized in {"refunded", "reversed", "revoked"}:
        return ("Payment refunded", f"Your {plan} payment via {provider} was refunded. Review your billing status in payment history.")
    if normalized == "expired":
        return ("Checkout expired", f"{provider} checkout expired before payment completed. Please start again from your plan selection.")
    return ("Payment not completed", f"{provider} could not complete your payment. No charge was completed. Try again or choose a different method.")


async def _missing_async(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="Stripe routes are not configured")


def _missing_sync(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="Stripe route dependency is not configured")


def _default_safe_float(value: Any, fallback: float = 0.0) -> float:
    return safe_amount_value(value, fallback)


def _default_fx_rate_for(_code: str, fallback: float = 1.0) -> float:
    return fallback


_get_subscription_lifecycle_state: Callable[[str], Awaitable[dict]] = _missing_async
_build_payment_record_from_tx: Callable[..., dict] = _missing_sync
_extract_tx_financials: Callable[[Dict[str, Any]], Dict[str, Any]] = _missing_sync
_send_payment_notification: Callable[..., Awaitable[dict]] = _missing_async
_mark_payment_notification_sent: Callable[[dict], Awaitable[None]] = _missing_async
_queue_payment_notification_recovery: Callable[[dict, str], Awaitable[None]] = _missing_async
_send_user_payment_failure_recovery_email: Callable[..., Awaitable[dict]] = _missing_async
_send_admin_payment_failure_alert: Callable[..., Awaitable[None]] = _missing_async
_compute_checkout_breakdown: Callable[..., Awaitable[dict]] = _missing_async
CheckoutPreviewRequest: Callable[..., object] = _missing_sync
_safe_float: Callable[[Any, float], float] = _default_safe_float
_fx_rate_for: Callable[[str, float], float] = _default_fx_rate_for


def _stripe_transition_event(state: str, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "state": str(state or "unknown"),
        "source": "stripe_routes",
        "detail": str(detail or "")[:300],
        "meta": meta or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _append_stripe_transition(session_id: str, state: str, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
    if not session_id:
        return
    event = _stripe_transition_event(state, detail, meta)
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "checkout_state": event["state"],
                "checkout_state_updated_at": event["created_at"],
                "updated_at": event["created_at"],
            },
            "$push": {
                "checkout_state_history": {
                    "$each": [event],
                    "$slice": -40,
                }
            },
        },
    )


def configure_stripe_routes(
    *,
    stripe_api_key: str,
    stripe_webhook_secret: str,
    zero_decimal_currencies: set[str],
    get_subscription_lifecycle_state: Callable[[str], Awaitable[dict]],
    build_payment_record_from_tx: Callable[..., dict],
    extract_tx_financials: Callable[[Dict[str, Any]], Dict[str, Any]],
    send_payment_notification: Callable[..., Awaitable[dict]],
    mark_payment_notification_sent: Callable[[dict], Awaitable[None]],
    queue_payment_notification_recovery: Callable[[dict, str], Awaitable[None]],
    send_user_payment_failure_recovery_email: Callable[..., Awaitable[dict]],
    send_admin_payment_failure_alert: Callable[..., Awaitable[None]],
    compute_checkout_breakdown: Callable[..., Awaitable[dict]],
    checkout_preview_request: Callable[..., object],
    safe_float: Callable[[Any, float], float],
    fx_rate_for: Callable[[str, float], float],
    route_logger: Optional[logging.Logger] = None,
) -> None:
    global STRIPE_API_KEY, STRIPE_WEBHOOK_SECRET, ZERO_DECIMAL_CURRENCIES, logger
    global _get_subscription_lifecycle_state, _build_payment_record_from_tx, _extract_tx_financials
    global _send_payment_notification, _mark_payment_notification_sent, _queue_payment_notification_recovery
    global _send_user_payment_failure_recovery_email, _send_admin_payment_failure_alert
    global _compute_checkout_breakdown, CheckoutPreviewRequest, _safe_float, _fx_rate_for

    STRIPE_API_KEY = stripe_api_key or ""
    STRIPE_WEBHOOK_SECRET = stripe_webhook_secret or ""
    ZERO_DECIMAL_CURRENCIES = set(zero_decimal_currencies)
    _get_subscription_lifecycle_state = get_subscription_lifecycle_state
    _build_payment_record_from_tx = build_payment_record_from_tx
    _extract_tx_financials = extract_tx_financials
    _send_payment_notification = send_payment_notification
    _mark_payment_notification_sent = mark_payment_notification_sent
    _queue_payment_notification_recovery = queue_payment_notification_recovery
    _send_user_payment_failure_recovery_email = send_user_payment_failure_recovery_email
    _send_admin_payment_failure_alert = send_admin_payment_failure_alert
    _compute_checkout_breakdown = compute_checkout_breakdown
    CheckoutPreviewRequest = checkout_preview_request
    _safe_float = safe_float
    _fx_rate_for = fx_rate_for
    if route_logger is not None:
        logger = route_logger


async def create_stripe_checkout_response(
    *,
    checkout_request,
    http_request: Request,
    user,
    plan: dict,
    saved_card: Optional[dict],
    saved_card_meta: dict,
    amount: float,
    product_type: str,
    jurisdiction: dict,
    base_url: str,
) -> dict:
    try:
        webhook_url = f"{base_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

        success_url = f"{base_url}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/subscription/plans?status=cancelled&gateway=stripe"

        req_currency = checkout_request.currency.upper() if checkout_request.currency else "USD"
        preview = await _compute_checkout_breakdown(
            user,
            http_request,
            CheckoutPreviewRequest(
                plan_id=checkout_request.plan_id,
                billing_period=checkout_request.billing_period,
                payment_method="stripe",
                currency=req_currency,
                country_code=checkout_request.country_code,
                state_code=checkout_request.state_code,
                postal_code=checkout_request.postal_code,
                product_type=checkout_request.product_type,
                preferred_language=checkout_request.preferred_language,
                browser_language=checkout_request.browser_language,
                browser_languages=checkout_request.browser_languages,
            ),
            enforce_methods=("stripe", "paypal", "fedapay"),
        )
        internal = preview.get("internal", {})
        financials = internal.get("financials", {})
        tax_quote = internal.get("tax_quote", {})
        checkout_currency = internal.get("checkout_currency", "usd")
        localization_context = preview.get("localization_context", {})
        checkout_amount = financials["total_amount"]
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"

        stripe_checkout_request = CheckoutSessionRequest(
            amount=checkout_amount,
            currency=checkout_currency,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": user.user_id,
                "plan_id": checkout_request.plan_id,
                "billing_period": checkout_request.billing_period,
                "email": user.email,
                "original_usd_amount": str(amount),
                "display_currency": req_currency,
                "resolved_language": localization_context.get("resolved_language", "en"),
                "transaction_id": transaction_id,
                "product_type": product_type,
                "jurisdiction_country": jurisdiction.get("country", ""),
                "jurisdiction_state": jurisdiction.get("state", ""),
                "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
                **saved_card_meta,
            },
            payment_methods=["card"],
        )
        session = await stripe_checkout.create_checkout_session(stripe_checkout_request)

        await db.payment_transactions.insert_one(
            {
                "transaction_id": transaction_id,
                "session_id": session.session_id,
                "user_id": user.user_id,
                "plan_id": checkout_request.plan_id,
                "billing_period": checkout_request.billing_period,
                "amount": amount,
                "amount_local": checkout_amount,
                "currency": checkout_currency,
                "original_usd_amount": amount,
                "fx_rate": preview.get("fx_rate", _fx_rate_for(checkout_currency.upper(), 1.0)),
                "fx_base_currency": preview.get("fx_base_currency", "USD"),
                "provider": "stripe",
                "payment_method": "stripe",
                "payment_status": "initiated",
                "subtotal": financials["subtotal"],
                "tax_amount": financials["tax_amount"],
                "processing_fee": financials["processing_fee"],
                "amount_gross": financials["amount_gross"],
                "amount_net": financials["amount_net"],
                "total_amount": financials["total_amount"],
                "tax_rate": _safe_float(tax_quote.get("tax_rate", 0), 0.0),
                "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
                "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
                "tax_breakdown": tax_quote.get("tax_breakdown", []),
                "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
                "product_type": tax_quote.get("product_type", product_type),
                "fee_pass_through": True,
                "locale": localization_context.get("resolved_language", "en"),
                "preferred_language": localization_context.get("resolved_language", "en"),
                "localization_context": localization_context,
                "saved_card_id": saved_card.get("card_id") if saved_card else None,
                "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
                "saved_card_type": saved_card.get("card_type") if saved_card else None,
                "status": "initiated",
                "checkout_state": "handoff_ready",
                "checkout_state_updated_at": datetime.now(timezone.utc).isoformat(),
                "checkout_state_history": [
                    _stripe_transition_event("created", "Stripe checkout transaction created"),
                    _stripe_transition_event("handoff_ready", "Stripe checkout URL generated"),
                ],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        await log_tax_calculation(
            db,
            transaction_id=transaction_id,
            provider="stripe",
            user_id=user.user_id,
            payload={
                "phase": "checkout_create",
                "tax_quote": tax_quote,
                "financials": financials,
                "currency": checkout_currency.upper(),
            },
        )
        await append_financial_ledger_entry(
            db,
            event_type="checkout_initiated",
            transaction_id=transaction_id,
            provider="stripe",
            user_id=user.user_id,
            payload={
                "status": "initiated",
                "payment_session": session.session_id,
                "financials": financials,
                "jurisdiction": tax_quote.get("jurisdiction", preview.get("jurisdiction", {})),
                "product_type": preview.get("product_type", product_type),
                "saved_card": saved_card,
            },
        )

        preview.pop("internal", None)
        return {
            "checkout_url": session.url,
            "session_id": session.session_id,
            "payment_method": "stripe",
            "currency": checkout_currency,
            "saved_card": saved_card,
            "checkout_breakdown": preview,
        }
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=400, detail=f"Stripe checkout failed: {str(e)}")

def _merge_stripe_provider_financials(existing_tx: Dict[str, Any], stripe_financials: Dict[str, Any]) -> Dict[str, Any]:
    existing_subtotal = _safe_float(existing_tx.get("subtotal", existing_tx.get("amount", 0)), 0.0)
    existing_tax = _safe_float(existing_tx.get("tax_amount", 0), 0.0)
    existing_fee = _safe_float(existing_tx.get("processing_fee", 0), 0.0)

    provider_subtotal = _safe_float(stripe_financials.get("subtotal", existing_subtotal), existing_subtotal)
    provider_tax = _safe_float(stripe_financials.get("tax_amount", existing_tax), existing_tax)
    provider_fee = _safe_float(stripe_financials.get("processing_fee", existing_fee), existing_fee)

    # Preserve precomputed tax/fee when provider payload doesn't include reliable values.
    if provider_tax <= 0 and existing_tax > 0:
        provider_tax = existing_tax
    if provider_fee <= 0 and existing_fee > 0:
        provider_fee = existing_fee

    computed = build_financial_totals(
        subtotal=provider_subtotal,
        tax_amount=provider_tax,
        processing_fee=provider_fee,
        fee_pass_through=bool(existing_tx.get("fee_pass_through", True)),
    )

    merged = {
        "currency": stripe_financials.get("currency", existing_tx.get("currency", "usd")).lower(),
        "subtotal": computed["subtotal"],
        "tax_amount": computed["tax_amount"],
        "processing_fee": computed["processing_fee"],
        "amount_gross": computed["amount_gross"],
        "amount_net": computed["amount_net"],
        "total_amount": computed["total_amount"],
        "provider_payment_intent_id": stripe_financials.get("provider_payment_intent_id") or existing_tx.get("provider_payment_intent_id"),
    }
    return merged


async def _fetch_stripe_session_financials(session_id: str) -> Dict[str, Any]:
    if not STRIPE_API_KEY or not session_id:
        return {}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            session_resp = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                auth=(STRIPE_API_KEY, ""),
                params={"expand[]": ["payment_intent"]},
            )
            if session_resp.status_code != 200:
                return {}
            session = session_resp.json() if isinstance(session_resp.json(), dict) else {}

            currency = str(session.get("currency", "usd")).upper()
            divisor = 1 if currency in ZERO_DECIMAL_CURRENCIES else 100
            subtotal = _safe_float(session.get("amount_subtotal", 0), 0.0) / divisor
            total = _safe_float(session.get("amount_total", 0), 0.0) / divisor
            tax_amount = _safe_float((session.get("total_details") or {}).get("amount_tax", 0), 0.0) / divisor
            gross = subtotal + tax_amount
            payment_intent = session.get("payment_intent", {})
            payment_intent_id = payment_intent.get("id") if isinstance(payment_intent, dict) else payment_intent
            processing_fee = 0.0

            if payment_intent_id:
                pi_resp = await client.get(
                    f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}",
                    auth=(STRIPE_API_KEY, ""),
                    params={"expand[]": ["charges.data.balance_transaction"]},
                )
                if pi_resp.status_code == 200:
                    pi = pi_resp.json() if isinstance(pi_resp.json(), dict) else {}
                    charges = (pi.get("charges") or {}).get("data", []) if isinstance(pi, dict) else []
                    if charges:
                        balance_tx = (charges[0] or {}).get("balance_transaction", {}) or {}
                        processing_fee = _safe_float(balance_tx.get("fee", 0), 0.0) / divisor

            return {
                "currency": currency,
                "subtotal": round(subtotal, 2),
                "tax_amount": round(tax_amount, 2),
                "amount_gross": round(gross, 2),
                "total_amount": round(total or gross, 2),
                "processing_fee": round(processing_fee, 2),
                "amount_net": round((total or gross) - processing_fee, 2),
                "provider_payment_intent_id": payment_intent_id,
            }
    except Exception as exc:
        logger.warning(f"Stripe session financial fetch failed for {session_id}: {exc}")
        return {}


@router.get("/subscriptions/checkout-status/{session_id}")
async def get_checkout_status(session_id: str, request: Request):
    """Poll Stripe checkout session status after redirect back."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    try:
        stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
        status = await stripe_checkout.get_checkout_status(session_id)

        txn = await db.payment_transactions.find_one({"session_id": session_id})
        if txn and status.payment_status == "paid":
            already_completed = txn.get("payment_status") in ("completed", "paid", "succeeded")
            notification_already_sent = txn.get("notification_sent", False)

            metadata = status.metadata or {}
            user_id = metadata.get("user_id")
            plan_id = metadata.get("plan_id")
            billing_period = metadata.get("billing_period", "monthly")

            if user_id and plan_id:
                plan = await get_subscription_plan_from_gps(plan_id)
                if plan:
                    # Activate subscription if webhook hasn't already done it
                    if not already_completed:
                        lifecycle_context = await _get_subscription_lifecycle_state(user_id)
                        end_date = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)

                        await db.users.update_one(
                            {"user_id": user_id},
                            {
                                "$set": {
                                    "subscription_plan": plan_id,
                                    "subscription_status": "active",
                                    "subscription_end_date": end_date,
                                    "updated_at": datetime.now(timezone.utc),
                                }
                            },
                        )
                        txn = {**txn, **lifecycle_context}

                        await db.payment_transactions.update_one(
                            {"session_id": session_id}, {"$set": {"payment_status": "completed"}}
                        )
                        await _append_stripe_transition(
                            session_id,
                            state="activated",
                            detail="Stripe checkout-status endpoint activated subscription",
                            meta={"path": "checkout_status"},
                        )

                    # Send notification only if webhook hasn't already sent it
                    if not notification_already_sent:
                        end_date = (
                            await db.users.find_one({"user_id": user_id}, {"_id": 0, "subscription_end_date": 1})
                        ) or {}
                        end_dt = end_date.get("subscription_end_date") or (
                            datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)
                        )
                        amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]
                        ticket_id = f"STR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                        email = metadata.get("email", "")
                        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})
                        user_name = user_doc.get("name", "") if user_doc else ""
                        renewal_date = end_dt.strftime("%b %d, %Y") if hasattr(end_dt, "strftime") else str(end_dt)[:10]
                        # Fetch currency data from transaction record
                        txn_currency = txn.get("currency", "usd").upper()
                        txn_amount_local = txn.get("amount_local", 0)
                        try:
                            await _send_payment_notification(
                                user_id, email, user_name, plan["name"],
                                txn.get("amount_gross", amount), "stripe", ticket_id, billing_period, renewal_date,
                                currency=txn_currency, amount_local=txn_amount_local,
                                transaction_context=txn,
                            )
                            await _mark_payment_notification_sent({"session_id": session_id})
                        except Exception as exc:
                            logger.error(f"Stripe checkout-status notification error: {exc}")
                            await _queue_payment_notification_recovery(txn, str(exc))

        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency,
        }
    except Exception as e:
        err = str(e)
        logger.error(f"Checkout status error: {err}")
        lowered = err.lower()
        if "no such checkout.session" in lowered or "resource_missing" in lowered or "does not exist" in lowered:
            raise HTTPException(status_code=404, detail="Checkout session not found")
        raise HTTPException(status_code=500, detail="Failed to check checkout status")


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook handler — verifies payment, activates subscription, sends notifications."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_secret=STRIPE_WEBHOOK_SECRET, webhook_url="")
    try:
        event = await stripe_checkout.handle_webhook(payload, signature)
    except Exception as exc:
        logger.error(f"Stripe webhook error: {exc}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = getattr(event, "event_type", None) if not isinstance(event, dict) else event.get("event_type")
    session_id = getattr(event, "session_id", None) if not isinstance(event, dict) else event.get("session_id")
    payment_status = (
        getattr(event, "payment_status", None) if not isinstance(event, dict) else event.get("payment_status")
    )

    logger.info(f"Stripe webhook received: event_type={event_type}, session_id={session_id}, payment_status={payment_status}")

    if not session_id:
        return {"received": True}

    update_payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "webhook_verified": True}
    if payment_status:
        update_payload["payment_status"] = payment_status

    await db.payment_transactions.update_one({"session_id": session_id}, {"$set": update_payload})
    await _append_stripe_transition(
        session_id,
        state="provider_callback_received",
        detail=f"Stripe webhook received: {event_type}",
        meta={"payment_status": payment_status or "unknown"},
    )

    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        logger.warning(f"Stripe webhook: no transaction found for session_id={session_id}")
        return {"received": True}

    user_id = tx.get("user_id")
    plan_id = tx.get("plan_id", "basic")
    billing_period = tx.get("billing_period", "monthly")

    # ── PAYMENT SUCCESS ──
    if payment_status in ("paid", "complete", "completed", "succeeded"):
        end_date = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)
        plan = await get_subscription_plan_from_gps(plan_id)
        stripe_financials = await _fetch_stripe_session_financials(session_id)
        tx_update = {
            "provider": "stripe",
            "status": "completed",
            "payment_status": "completed",
            "fee_pass_through": True,
        }
        if stripe_financials:
            merged_financials = _merge_stripe_provider_financials(tx, stripe_financials)
            tx_update.update(
                {
                    **merged_financials,
                }
            )
        else:
            fallback_financials = _extract_tx_financials(tx)
            tx_update.update(fallback_financials)

        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": tx_update})
        await _append_stripe_transition(
            session_id,
            state="activated",
            detail="Stripe webhook confirmed paid and activated subscription",
            meta={"event_type": event_type},
        )
        tx = {
            **tx,
            **tx_update,
            "session_id": session_id,
            "payment_id": tx.get("payment_id") or session_id,
            "transaction_id": tx.get("transaction_id") or session_id,
        }

        await append_financial_ledger_entry(
            db,
            event_type="provider_webhook_confirmed",
            transaction_id=tx.get("transaction_id"),
            provider="stripe",
            user_id=user_id,
            payload={
                "event_type": event_type,
                "session_id": session_id,
                "financials": {
                    "subtotal": tx.get("subtotal"),
                    "tax_amount": tx.get("tax_amount"),
                    "processing_fee": tx.get("processing_fee"),
                    "amount_gross": tx.get("amount_gross"),
                    "amount_net": tx.get("amount_net"),
                    "total_amount": tx.get("total_amount"),
                },
            },
        )

        existing_payment = await db.payments.find_one({"payment_id": tx.get("payment_id")}, {"_id": 0, "payment_id": 1})
        if not existing_payment:
            await db.payments.insert_one(_build_payment_record_from_tx(tx, status="completed"))

        await db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "subscription_plan": plan_id,
                    "subscription_status": "active",
                    "subscription_end_date": end_date,
                    "payment_verified": True,
                    "webhook_verified": True,
                    "last_payment_id": session_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        logger.info(f"Stripe webhook: user {user_id} subscription activated ({plan_id})")

        # Track A/B test conversions: mark upgrade in prompt experiments
        try:
            from routes.ab_testing import check_user_returned
            await check_user_returned(user_id)
        except Exception:
            pass
        try:
            upgrade_event = {
                "event_id": f"pevt_{uuid.uuid4().hex[:10]}",
                "experiment_id": "__auto_upgrade__",
                "variant_id": "__upgrade__",
                "user_id": user_id,
                "event": "upgrade",
                "metadata": {"plan": plan_id, "method": "stripe", "billing": billing_period},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.prompt_experiment_events.insert_one(upgrade_event)
            # Also mark any onboarding A/B assignment as converted
            await db.ab_assignments.update_many(
                {"user_id": user_id, "converted": False},
                {"$set": {"converted": True, "converted_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception as e:
            logger.warning(f"A/B conversion tracking non-fatal: {e}")

        # Log to audit
        await db.subscription_audit_log.insert_one(
            {
                "user_id": user_id,
                "action": "webhook_verified_activation",
                "plan_id": plan_id,
                "session_id": session_id,
                "payment_status": payment_status,
                "timestamp": datetime.now(timezone.utc),
            }
        )

        # Send payment confirmation email + in-app notification
        if plan and user_id:
            try:
                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                if user_doc:
                    amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]
                    ticket_id = f"STR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                    renewal_date = end_date.strftime("%b %d, %Y")
                    # Fetch currency data from transaction record
                    txn_currency = tx.get("currency", "usd").upper()
                    txn_amount_local = tx.get("amount_local", 0)
                    await _send_payment_notification(
                        user_id=user_id,
                        email=user_doc.get("email", ""),
                        user_name=user_doc.get("name", ""),
                        plan_name=plan["name"],
                        amount=tx.get("amount_gross", amount),
                        payment_method="stripe",
                        ticket_id=ticket_id,
                        billing_cycle=billing_period,
                        renewal_date=renewal_date,
                        currency=txn_currency,
                        amount_local=txn_amount_local,
                        transaction_context=tx,
                    )
                    await _mark_payment_notification_sent({"session_id": session_id})
                    logger.info(f"Stripe webhook: payment notification sent to user {user_id}")
            except Exception as e:
                logger.error(f"Stripe webhook notification error: {e}")
                await _queue_payment_notification_recovery(tx, str(e))

    # ── PAYMENT FAILED / EXPIRED ──
    elif payment_status in ("failed", "expired", "unpaid", "canceled"):
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": payment_status, "notification_sent": payment_status != "expired"}}
        )
        await _append_stripe_transition(
            session_id,
            state="failed",
            detail=f"Stripe webhook reported failure status: {payment_status}",
            meta={"event_type": event_type},
        )

        plan = await get_subscription_plan_from_gps(plan_id)
        plan_name = plan["name"] if plan else plan_id
        amount = 0
        if plan:
            amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]

        if payment_status == "expired":
            await dispatch_subscription_expiry_notification(
                user_id,
                source_provider="stripe",
                reason="expired",
                plan_name_override=plan_name,
                transaction_filter={"session_id": session_id},
            )
            logger.info(f"Stripe webhook: unified expiry notification sent for user {user_id}")
        else:
            try:
                from utils.notification_helper import create_notification
                title, message = _build_provider_failure_copy("Stripe", payment_status, plan_name)
                await create_notification(
                    user_id,
                    title,
                    message,
                    notif_type="payment_failed",
                    data={"session_id": session_id, "plan_id": plan_id, "amount": amount},
                )
            except Exception as e:
                logger.warning(f"Stripe failed notification error: {e}")
            logger.info(f"Stripe webhook: payment failed notification for user {user_id}, status={payment_status}")

        # Send failure email with recovery link
        user_email_for_admin = ""
        if is_email_configured():
            try:
                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                if user_doc and user_doc.get("email"):
                    user_email_for_admin = user_doc["email"]
                    txn = await db.payment_transactions.find_one(
                        {"session_id": session_id}, {"_id": 0, "currency": 1, "amount_local": 1, "billing_period": 1}
                    )
                    txn_currency = (txn.get("currency", "usd") if txn else "usd").upper()
                    txn_amount_local = txn.get("amount_local", 0) if txn else 0
                    bp = txn.get("billing_period", "monthly") if txn else "monthly"
                    recovery_dispatch = await _send_user_payment_failure_recovery_email(
                        user_id=user_id,
                        user_email=user_doc["email"],
                        user_name=user_doc.get("name", ""),
                        plan_id=plan_id,
                        plan_name=plan_name,
                        billing_period=bp,
                        payment_method="stripe",
                        amount_usd=amount,
                        currency=txn_currency,
                        amount_local=txn_amount_local,
                        session_id=session_id,
                    )
                    if recovery_dispatch.get("sent"):
                        logger.info(f"Stripe webhook: recovery email sent to {user_doc['email']}")
                    elif recovery_dispatch.get("reason") == "daily_throttled":
                        logger.info(
                            "Stripe webhook: recovery email throttled for user=%s (last_email_at=%s)",
                            user_id,
                            recovery_dispatch.get("last_email_at"),
                        )
            except Exception as e:
                logger.error(f"Stripe webhook recovery email error: {e}")

        try:
            if not user_email_for_admin:
                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
                user_email_for_admin = (user_doc or {}).get("email", "")
            await _send_admin_payment_failure_alert(
                customer_email=user_email_for_admin,
                plan_name=plan_name,
                payment_method="stripe",
                reason=payment_status,
                amount=amount,
                amount_local=txn_amount_local if 'txn_amount_local' in locals() else 0,
                currency=txn_currency if 'txn_currency' in locals() else "USD",
                reference_id=session_id,
            )
        except Exception as e:
            logger.warning(f"Stripe admin failure alert error: {e}")

    return {"received": True}


# ── Admin: Stripe production-behavior E2E simulator ──
# Shared orchestration lives in payments_simulation_core.run_provider_payment_simulation.

class StripeSimulationRequest(ProviderSimulationRequest):
    pass


@router.post("/admin/payments/simulate-stripe-production-e2e")
async def simulate_stripe_production_e2e(body: StripeSimulationRequest, request: Request):
    admin = await get_current_user(request)
    if not admin or not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await run_provider_payment_simulation(
        body,
        provider="stripe",
        fee_provider="stripe",
        tx_payment_method="stripe",
        payment_method_label="stripe",
        ticket_prefix="STR",
        tx_prefix="sim_stripe",
        ledger_event_type="provider_webhook_confirmed",
        provider_display="Stripe",
        get_plan=get_subscription_plan_from_gps,
        send_payment_notification=_send_payment_notification,
        queue_payment_notification_recovery=_queue_payment_notification_recovery,
        build_payment_record_from_tx=_build_payment_record_from_tx,
        failure_copy=_build_provider_failure_copy,
        append_transition=_append_stripe_transition,
        extra_user_fields={"webhook_verified": True},
    )
