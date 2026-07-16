"""PayPal JS SDK and webhook routes extracted from payments.py.

Provider-level PayPal API helpers remain in payments_provider_paypal.py; this module
only owns route handlers and route orchestration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
import logging
import os
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from utils.email_service import is_email_configured
from .db import db, get_current_user
from .payments_catalog import get_subscription_plan_from_gps, require_paid_subscription_plan
from .payments_pricing_guard import safe_amount_value as _safe_amount_value
from .payments_simulation_core import ProviderSimulationRequest, run_provider_payment_simulation
from utils.tax_compliance_engine import append_financial_ledger_entry, build_financial_totals, log_tax_calculation, resolve_product_type
from .subscription_enforcement import dispatch_subscription_expiry_notification


router = APIRouter()
logger = logging.getLogger("routes.payments.paypal_routes")

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_API_URL = "https://api-m.sandbox.paypal.com"
PAYPAL_SUPPORTED_CURRENCIES = {"USD"}
ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "XOF", "XAF"}


def _build_provider_failure_copy(provider_label: str, state: str, plan_name: str) -> tuple[str, str, str]:
    provider = provider_label or "Payment Gateway"
    plan = plan_name or "subscription"
    normalized = str(state or "failed").strip().lower()
    if normalized in {"cancelled", "canceled"}:
        return ("Checkout cancelled", f"{provider} checkout was cancelled before payment completed. No charge was completed.", "subscription_cancelled")
    if normalized in {"refunded", "reversed", "revoked"}:
        return ("Payment refunded", f"Your {plan} payment via {provider} was refunded. Review your billing status in payment history.", "payment_failed")
    return ("Payment not completed", f"{provider} could not complete your payment. No charge was completed. Try again or choose a different method.", "payment_failed")


async def _missing_user_resolver(_request: Request):
    raise HTTPException(status_code=503, detail="PayPal routes are not configured")


async def _missing_async(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="PayPal route dependency is not configured")


def _missing_sync(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="PayPal route dependency is not configured")


_get_user_from_request: Callable[[Request], Awaitable[object | None]] = _missing_user_resolver
_resolve_saved_card_for_checkout: Callable[..., Awaitable[dict | None]] = _missing_async
_compute_checkout_breakdown: Callable[..., Awaitable[dict]] = _missing_async
CheckoutPreviewRequest: Callable[..., object] = _missing_sync
_get_paypal_token: Callable[[], Awaitable[str]] = _missing_async
_capture_paypal_order: Callable[[str], Awaitable[dict]] = _missing_async
_verify_paypal_webhook: Callable[[Request, bytes], Awaitable[bool]] = _missing_async
_get_subscription_lifecycle_state: Callable[[str], Awaitable[dict]] = _missing_async
_build_payment_record_from_tx: Callable[..., dict] = _missing_sync
_send_payment_notification: Callable[..., Awaitable[dict]] = _missing_async
_mark_payment_notification_sent: Callable[[dict], Awaitable[None]] = _missing_async
_queue_payment_notification_recovery: Callable[[dict, str], Awaitable[None]] = _missing_async
_send_user_payment_failure_recovery_email: Callable[..., Awaitable[dict]] = _missing_async
_send_admin_payment_failure_alert: Callable[..., Awaitable[None]] = _missing_async
def _default_fx_rate_for(_code: str, fallback: float = 1.0) -> float:
    return fallback


def _default_safe_float(value: Any, fallback: float = 0.0) -> float:
    return _safe_amount_value(value, fallback)


_fx_rate_for: Callable[[str, float], float] = _default_fx_rate_for
_safe_float: Callable[[Any, float], float] = _default_safe_float


def configure_paypal_routes(
    *,
    get_user_from_request: Callable[[Request], Awaitable[object | None]],
    resolve_saved_card_for_checkout: Callable[..., Awaitable[dict | None]],
    compute_checkout_breakdown: Callable[..., Awaitable[dict]],
    checkout_preview_request: Callable[..., object],
    get_paypal_token: Callable[[], Awaitable[str]],
    capture_paypal_order: Callable[[str], Awaitable[dict]],
    verify_paypal_webhook: Callable[[Request, bytes], Awaitable[bool]],
    get_subscription_lifecycle_state: Callable[[str], Awaitable[dict]],
    build_payment_record_from_tx: Callable[..., dict],
    send_payment_notification: Callable[..., Awaitable[dict]],
    mark_payment_notification_sent: Callable[[dict], Awaitable[None]],
    queue_payment_notification_recovery: Callable[[dict, str], Awaitable[None]],
    send_user_payment_failure_recovery_email: Callable[..., Awaitable[dict]],
    send_admin_payment_failure_alert: Callable[..., Awaitable[None]],
    fx_rate_for: Callable[[str, float], float],
    safe_float: Callable[[Any, float], float],
    paypal_client_id: str,
    paypal_api_url: str,
    paypal_supported_currencies: set[str],
    zero_decimal_currencies: set[str],
    route_logger: Optional[logging.Logger] = None,
) -> None:
    global _get_user_from_request, _resolve_saved_card_for_checkout, _compute_checkout_breakdown, CheckoutPreviewRequest
    global _get_paypal_token, _capture_paypal_order, _verify_paypal_webhook, _get_subscription_lifecycle_state
    global _build_payment_record_from_tx, _send_payment_notification, _mark_payment_notification_sent
    global _queue_payment_notification_recovery, _send_user_payment_failure_recovery_email, _send_admin_payment_failure_alert
    global _fx_rate_for, _safe_float, PAYPAL_CLIENT_ID, PAYPAL_API_URL, PAYPAL_SUPPORTED_CURRENCIES, ZERO_DECIMAL_CURRENCIES, logger

    _get_user_from_request = get_user_from_request
    _resolve_saved_card_for_checkout = resolve_saved_card_for_checkout
    _compute_checkout_breakdown = compute_checkout_breakdown
    CheckoutPreviewRequest = checkout_preview_request
    _get_paypal_token = get_paypal_token
    _capture_paypal_order = capture_paypal_order
    _verify_paypal_webhook = verify_paypal_webhook
    _get_subscription_lifecycle_state = get_subscription_lifecycle_state
    _build_payment_record_from_tx = build_payment_record_from_tx
    _send_payment_notification = send_payment_notification
    _mark_payment_notification_sent = mark_payment_notification_sent
    _queue_payment_notification_recovery = queue_payment_notification_recovery
    _send_user_payment_failure_recovery_email = send_user_payment_failure_recovery_email
    _send_admin_payment_failure_alert = send_admin_payment_failure_alert
    _fx_rate_for = fx_rate_for
    _safe_float = safe_float
    PAYPAL_CLIENT_ID = paypal_client_id
    PAYPAL_API_URL = paypal_api_url
    PAYPAL_SUPPORTED_CURRENCIES = set(paypal_supported_currencies)
    ZERO_DECIMAL_CURRENCIES = set(zero_decimal_currencies)
    if route_logger is not None:
        logger = route_logger

# ── PayPal JS SDK Endpoints (for inline buttons) ──


@router.get("/paypal/client-id")
async def get_paypal_client_id():
    """Return PayPal client ID for JS SDK initialization."""
    return {
        "client_id": os.environ.get("PAYPAL_CLIENT_ID", ""),
        "currency": "USD",
        "supported_currencies": sorted(PAYPAL_SUPPORTED_CURRENCIES),
    }


@router.post("/paypal/create-order")
async def paypal_create_order(request: Request):
    """Create PayPal order for JS SDK buttons."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    plan_id = body.get("plan_id", "basic")
    billing_period = body.get("billing_period", "monthly")
    saved_card = await _resolve_saved_card_for_checkout(user.user_id, body.get("saved_card_id"))

    plan = await require_paid_subscription_plan(plan_id)

    amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]
    product_type = resolve_product_type(plan_id)
    preview = await _compute_checkout_breakdown(
        user,
        request,
        CheckoutPreviewRequest(
            plan_id=plan_id,
            billing_period=billing_period,
            payment_method="paypal",
            currency=str(body.get("currency") or "USD"),
            country_code=body.get("country_code"),
            state_code=body.get("state_code"),
            postal_code=body.get("postal_code"),
            product_type=product_type,
            preferred_language=body.get("preferred_language"),
            browser_language=body.get("browser_language"),
            browser_languages=body.get("browser_languages"),
        ),
        enforce_methods=("stripe", "paypal", "fedapay"),
    )
    internal = preview.get("internal", {})
    financials = internal.get("financials", {})
    tax_quote = internal.get("tax_quote", {})
    localization_context = preview.get("localization_context", {})
    jurisdiction = preview.get("jurisdiction", {})
    checkout_currency = str(preview.get("currency", "USD")).upper()

    try:
        try:
            access_token = await _get_paypal_token()
        except Exception:
            # PayPal credentials mismatch - use fallback
            order_id = f"PPORDER_{uuid.uuid4().hex[:12].upper()}"
            transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
            await db.payment_transactions.insert_one(
                {
                    "transaction_id": transaction_id,
                    "session_id": order_id,
                    "user_id": user.user_id,
                    "plan_id": plan_id,
                    "billing_period": billing_period,
                    "amount": amount,
                    "amount_local": financials.get("total_amount", amount),
                    "currency": checkout_currency.lower(),
                    "original_usd_amount": amount,
                    "fx_rate": preview.get("fx_rate", _fx_rate_for(checkout_currency, 1.0)),
                    "fx_base_currency": preview.get("fx_base_currency", "USD"),
                    "provider": "paypal_js",
                    "payment_method": "paypal_js",
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
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            await log_tax_calculation(
                db,
                transaction_id=transaction_id,
                provider="paypal_js",
                user_id=user.user_id,
                payload={"phase": "checkout_create", "tax_quote": tax_quote, "financials": financials},
            )
            return {"id": order_id, "status": "CREATED", "amount": amount, "fallback": True}

        def _fmt_money(value: float) -> str:
            precision = 0 if checkout_currency in ZERO_DECIMAL_CURRENCIES else 2
            return f"{_safe_float(value, 0.0):.{precision}f}"

        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": checkout_currency,
                        "value": _fmt_money(financials["total_amount"]),
                        "breakdown": {
                            "item_total": {"currency_code": checkout_currency, "value": _fmt_money(financials["subtotal"])},
                            "tax_total": {"currency_code": checkout_currency, "value": _fmt_money(financials["tax_amount"])},
                        },
                    },
                    "description": f"RealAICoach {plan['name']} - {billing_period.title()}",
                    "custom_id": f"{user.user_id}|{plan_id}|{billing_period}",
                }
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_API_URL}/v2/checkout/orders",
                json=order_data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"},
            )
            if response.status_code not in [200, 201]:
                logger.error(f"PayPal create order failed: {response.text}")
                # Fallback: return order data for client-side creation
                order_id = f"PPORDER_{uuid.uuid4().hex[:12].upper()}"
                transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
                await db.payment_transactions.insert_one(
                    {
                        "transaction_id": transaction_id,
                        "session_id": order_id,
                        "user_id": user.user_id,
                        "plan_id": plan_id,
                        "billing_period": billing_period,
                        "amount": amount,
                        "amount_local": financials.get("total_amount", amount),
                        "currency": checkout_currency.lower(),
                        "original_usd_amount": amount,
                        "fx_rate": preview.get("fx_rate", _fx_rate_for(checkout_currency, 1.0)),
                        "fx_base_currency": preview.get("fx_base_currency", "USD"),
                        "provider": "paypal_js",
                        "payment_method": "paypal_js",
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
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                await log_tax_calculation(
                    db,
                    transaction_id=transaction_id,
                    provider="paypal_js",
                    user_id=user.user_id,
                    payload={"phase": "checkout_create", "tax_quote": tax_quote, "financials": financials},
                )
                return {"id": order_id, "status": "CREATED", "amount": amount, "fallback": True}

            order = response.json()

        # Log the transaction
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
        await db.payment_transactions.insert_one(
            {
                "transaction_id": transaction_id,
                "session_id": order.get("id", ""),
                "user_id": user.user_id,
                "plan_id": plan_id,
                "billing_period": billing_period,
                "amount": amount,
                "amount_local": financials.get("total_amount", amount),
                "currency": checkout_currency.lower(),
                "original_usd_amount": amount,
                "fx_rate": preview.get("fx_rate", _fx_rate_for(checkout_currency, 1.0)),
                "fx_base_currency": preview.get("fx_base_currency", "USD"),
                "provider": "paypal_js",
                "payment_method": "paypal_js",
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
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await log_tax_calculation(
            db,
            transaction_id=transaction_id,
            provider="paypal_js",
            user_id=user.user_id,
            payload={"phase": "checkout_create", "tax_quote": tax_quote, "financials": financials},
        )

        return {"id": order.get("id"), "status": order.get("status")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PayPal create order error: {e}")
        # Graceful fallback
        order_id = f"PPORDER_{uuid.uuid4().hex[:12].upper()}"
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
        await db.payment_transactions.insert_one(
            {
                "transaction_id": transaction_id,
                "session_id": order_id,
                "user_id": user.user_id,
                "plan_id": plan_id,
                "billing_period": billing_period,
                "amount": amount,
                "currency": "usd",
                "provider": "paypal_js",
                "payment_method": "paypal_js",
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
                "saved_card_id": saved_card.get("card_id") if saved_card else None,
                "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
                "saved_card_type": saved_card.get("card_type") if saved_card else None,
                "status": "initiated",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await log_tax_calculation(
            db,
            transaction_id=transaction_id,
            provider="paypal_js",
            user_id=user.user_id,
            payload={"phase": "checkout_create", "tax_quote": tax_quote, "financials": financials},
        )
        return {"id": order_id, "status": "CREATED", "amount": amount, "fallback": True}


@router.post("/paypal/capture-order/{order_id}")
async def paypal_capture_order(order_id: str, request: Request):
    """Capture PayPal order after user approval (called by JS SDK)."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        capture = await _capture_paypal_order(order_id)

        status = capture.get("status", "")
        if status == "COMPLETED":
            tx_existing = await db.payment_transactions.find_one({"session_id": order_id}, {"_id": 0}) or {}
            # Get plan info from custom_id
            custom_id = ""
            capture_obj = {}
            for pu in capture.get("purchase_units", []):
                for cap in pu.get("payments", {}).get("captures", []):
                    custom_id = cap.get("custom_id", pu.get("custom_id", ""))
                    capture_obj = cap
                    break

            parts = custom_id.split("|") if custom_id else []
            plan_id = parts[1] if len(parts) > 1 else "basic"
            billing_period = parts[2] if len(parts) > 2 else "monthly"

            plan = await get_subscription_plan_from_gps(plan_id, default_plan_id="basic")
            amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]
            end_date = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)

            amount_block = (capture.get("purchase_units", [{}])[0] or {}).get("amount", {})
            amount_breakdown = amount_block.get("breakdown", {}) if isinstance(amount_block, dict) else {}
            subtotal_val = _safe_float(amount_breakdown.get("item_total", {}).get("value"), _safe_float(tx_existing.get("subtotal", amount), amount))
            tax_val = _safe_float(amount_breakdown.get("tax_total", {}).get("value"), _safe_float(tx_existing.get("tax_amount", 0), 0.0))
            fee_val = _safe_float(
                (capture_obj.get("seller_receivable_breakdown", {}) or {}).get("paypal_fee", {}).get("value"),
                _safe_float(tx_existing.get("processing_fee", 0), 0.0),
            )
            financials = build_financial_totals(
                subtotal=subtotal_val,
                tax_amount=tax_val,
                processing_fee=fee_val,
                fee_pass_through=True,
            )
            tx_update = {
                "payment_status": "completed",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "provider": "paypal",
                "fee_pass_through": True,
                "subtotal": financials["subtotal"],
                "tax_amount": financials["tax_amount"],
                "processing_fee": financials["processing_fee"],
                "amount_gross": financials["amount_gross"],
                "amount_net": financials["amount_net"],
                "total_amount": financials["total_amount"],
                "status": "completed",
                "provider_capture_payload": capture,
            }
            await db.payment_transactions.update_one({"session_id": order_id}, {"$set": tx_update})

            tx_final = {
                **tx_existing,
                **tx_update,
                "session_id": order_id,
                "user_id": user.user_id,
                "plan_id": plan_id,
                "billing_period": billing_period,
                "payment_method": "paypal_js",
                "payment_id": tx_existing.get("payment_id") or order_id,
                "currency": tx_existing.get("currency", "usd"),
                "transaction_id": tx_existing.get("transaction_id") or order_id,
            }
            await append_financial_ledger_entry(
                db,
                event_type="provider_capture_completed",
                transaction_id=tx_final.get("transaction_id"),
                provider="paypal",
                user_id=user.user_id,
                payload={
                    "financials": financials,
                    "provider_event": "capture_order",
                    "order_id": order_id,
                    "capture_id": capture_obj.get("id"),
                },
            )

            # Activate subscription
            lifecycle_context = await _get_subscription_lifecycle_state(user.user_id)
            await db.users.update_one(
                {"user_id": user.user_id},
                {
                    "$set": {
                        "subscription_plan": plan_id,
                        "subscription_status": "active",
                        "subscription_end_date": end_date,
                        "payment_verified": True,
                        "last_payment_id": order_id,
                        "last_payment_method": "paypal_js",
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            tx_final = {**tx_final, **lifecycle_context}

            existing_payment = await db.payments.find_one({"payment_id": tx_final.get("payment_id")}, {"_id": 0, "payment_id": 1})
            if not existing_payment:
                await db.payments.insert_one(_build_payment_record_from_tx(tx_final, status="completed"))

            # Broadcast real-time payment event
            try:
                from utils.ws_manager import broadcast_data_change

                await broadcast_data_change("payments", "created", user.user_id)
                await broadcast_data_change("subscription", "updated", user.user_id)
            except Exception:
                pass

            # Send notification
            ticket_id = f"PP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
            renewal_date = end_date.strftime("%b %d, %Y")
            try:
                await _send_payment_notification(
                    user.user_id,
                    user.email,
                    getattr(user, "name", ""),
                    plan["name"],
                    tx_final.get("amount_gross", amount),
                    "PayPal",
                    ticket_id,
                    billing_period,
                    renewal_date,
                    transaction_context=tx_final,
                )
                await _mark_payment_notification_sent({"session_id": order_id})
            except Exception as exc:
                logger.error(f"PayPal capture-order notification dispatch failed for {order_id}: {exc}")
                await _queue_payment_notification_recovery(tx_final, str(exc))

            return {
                "status": "COMPLETED",
                "subscription_plan": plan_id,
                "subscription_end_date": end_date.isoformat(),
                "message": f"Successfully subscribed to {plan['name']}!",
            }

        return {"status": status, "details": capture}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PayPal capture error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── PayPal Webhook ──

@router.post("/webhook/paypal")
@router.post("/payments/paypal/webhook")
async def paypal_webhook(request: Request):
    """Handle PayPal webhook events. Always returns 200 to acknowledge receipt."""
    try:
        raw_body = await request.body()

        # Verify signature (log warning but process anyway)
        sig_valid = await _verify_paypal_webhook(request, raw_body)
        if not sig_valid:
            logger.warning("PayPal webhook signature verification failed")

        # Parse payload
        payload = {}
        if raw_body and raw_body.strip():
            try:
                import json as _json

                payload = _json.loads(raw_body)
            except Exception:
                logger.warning(f"PayPal webhook: non-JSON body ({len(raw_body)} bytes)")
                return JSONResponse({"received": True}, status_code=200)

        if not payload:
            logger.info("PayPal webhook: ping/empty payload acknowledged")
            return JSONResponse({"received": True}, status_code=200)

        event_type = payload.get("event_type", "")
        resource = payload.get("resource", {})
        event_id = payload.get("id", "")

        logger.info(f"PayPal webhook: event={event_type}, event_id={event_id}")

        # ── PAYMENT.CAPTURE.COMPLETED ──
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id", "")
            capture_id = resource.get("id", "")
            resource.get("status", "")
            amount_value = resource.get("amount", {}).get("value", "0")
            custom_id = resource.get("custom_id", "")

            logger.info(
                f"PayPal capture completed: order={order_id}, capture={capture_id}, amount={amount_value}, custom_id={custom_id}"
            )

            if order_id:
                tx = await db.payment_transactions.find_one({"session_id": order_id}, {"_id": 0})
                if tx:
                    already_completed = tx.get("payment_status") == "completed"
                    notification_already_sent = tx.get("notification_sent", False)

                    seller_breakdown = resource.get("seller_receivable_breakdown", {}) or {}
                    fee_val = _safe_float(
                        (seller_breakdown.get("paypal_fee") or {}).get("value"),
                        _safe_float(tx.get("processing_fee", 0), 0.0),
                    )
                    gross_val = _safe_float(
                        (seller_breakdown.get("gross_amount") or {}).get("value"),
                        _safe_float(resource.get("amount", {}).get("value"), _safe_float(tx.get("amount_gross", tx.get("total_amount", 0)), 0.0)),
                    )
                    tax_val = _safe_float(tx.get("tax_amount", 0), 0.0)
                    subtotal_val = _safe_float(tx.get("subtotal", max(gross_val - tax_val, 0.0)), max(gross_val - tax_val, 0.0))
                    financials = build_financial_totals(
                        subtotal=subtotal_val,
                        tax_amount=tax_val,
                        processing_fee=fee_val,
                        fee_pass_through=True,
                    )
                    tx_common_update = {
                        "paypal_capture_id": capture_id,
                        "webhook_received_at": datetime.now(timezone.utc).isoformat(),
                        "provider": "paypal",
                        "fee_pass_through": True,
                        "subtotal": financials["subtotal"],
                        "tax_amount": financials["tax_amount"],
                        "processing_fee": financials["processing_fee"],
                        "amount_gross": financials["amount_gross"],
                        "amount_net": financials["amount_net"],
                        "total_amount": financials["total_amount"],
                        "status": "completed",
                        "provider_capture_payload": resource,
                    }

                    # Update transaction status
                    if not already_completed:
                        await db.payment_transactions.update_one(
                            {"session_id": order_id},
                            {
                                "$set": {
                                    "payment_status": "completed",
                                    **tx_common_update,
                                }
                            },
                        )
                    else:
                        await db.payment_transactions.update_one(
                            {"session_id": order_id},
                            {
                                "$set": {
                                    "webhook_verified": True,
                                    **tx_common_update,
                                }
                            },
                        )

                    tx = {
                        **tx,
                        **tx_common_update,
                        "payment_status": "completed",
                        "payment_id": tx.get("payment_id") or order_id,
                        "transaction_id": tx.get("transaction_id") or order_id,
                    }

                    await append_financial_ledger_entry(
                        db,
                        event_type="provider_webhook_confirmed",
                        transaction_id=tx.get("transaction_id"),
                        provider="paypal",
                        user_id=tx.get("user_id", ""),
                        payload={"event_id": event_id, "order_id": order_id, "financials": financials},
                    )

                    existing_payment = await db.payments.find_one({"payment_id": tx.get("payment_id")}, {"_id": 0, "payment_id": 1})
                    if not existing_payment:
                        await db.payments.insert_one(_build_payment_record_from_tx(tx, status="completed"))

                    user_id = tx.get("user_id")
                    plan_id = tx.get("plan_id", "basic")
                    billing_period = tx.get("billing_period", "monthly")
                    plan = await get_subscription_plan_from_gps(plan_id)

                    # Activate subscription if capture didn't already do it
                    if not already_completed and plan and user_id:
                        lifecycle_context = await _get_subscription_lifecycle_state(user_id)
                        end_date = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)
                        await db.users.update_one(
                            {"user_id": user_id},
                            {
                                "$set": {
                                    "subscription_plan": plan_id,
                                    "subscription_status": "active",
                                    "subscription_end_date": end_date,
                                    "payment_verified": True,
                                    "webhook_verified": True,
                                    "updated_at": datetime.now(timezone.utc),
                                }
                            },
                        )
                        tx = {**tx, **lifecycle_context}
                        logger.info(f"PayPal webhook: user {user_id} subscription activated ({plan_id})")

                        # Track A/B test conversions
                        try:
                            from routes.ab_testing import check_user_returned
                            await check_user_returned(user_id)
                        except Exception:
                            pass
                        try:
                            await db.prompt_experiment_events.insert_one({
                                "event_id": f"pevt_{uuid.uuid4().hex[:10]}",
                                "experiment_id": "__auto_upgrade__",
                                "variant_id": "__upgrade__",
                                "user_id": user_id,
                                "event": "upgrade",
                                "metadata": {"plan": plan_id, "method": "paypal", "billing": billing_period},
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            })
                            await db.ab_assignments.update_many(
                                {"user_id": user_id, "converted": False},
                                {"$set": {"converted": True, "converted_at": datetime.now(timezone.utc).isoformat()}},
                            )
                        except Exception:
                            pass

                    # Send notification if not already sent by capture endpoint
                    if not notification_already_sent and plan and user_id:
                        try:
                            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                            if user_doc:
                                amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]
                                end_dt = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)
                                ticket_id = f"PP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                                txn_currency = tx.get("currency", "usd").upper()
                                txn_amount_local = tx.get("amount_local", 0)
                                await _send_payment_notification(
                                    user_id=user_id,
                                    email=user_doc.get("email", ""),
                                    user_name=user_doc.get("name", ""),
                                    plan_name=plan["name"],
                                    amount=tx.get("amount_gross", amount),
                                    payment_method="PayPal",
                                    ticket_id=ticket_id,
                                    billing_cycle=billing_period,
                                    renewal_date=end_dt.strftime("%b %d, %Y"),
                                    currency=txn_currency,
                                    amount_local=txn_amount_local,
                                    transaction_context=tx,
                                )
                                await _mark_payment_notification_sent({"session_id": order_id})
                                logger.info(f"PayPal webhook: payment notification sent to {user_doc.get('email')}")
                        except Exception as e:
                            logger.error(f"PayPal webhook notification error: {e}")
                            await _queue_payment_notification_recovery(tx, str(e))
                    else:
                        logger.info(f"PayPal webhook: notification already sent for order {order_id}")
                    logger.info(f"PayPal webhook: transaction {order_id} processed")

        # ── BILLING.SUBSCRIPTION / PAYMENT.SALE failure and cancellation states ──
        elif event_type in (
            "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
            "BILLING.SUBSCRIPTION.CANCELLED",
            "BILLING.SUBSCRIPTION.EXPIRED",
            "PAYMENT.SALE.REVERSED",
            "PAYMENT.SALE.REFUNDED",
        ):
            resource_id = resource.get("id", "")
            custom_id = resource.get("custom_id", "") or resource.get("custom", "")
            user_id = ""
            plan_id = "basic"
            billing_period = "monthly"

            if custom_id and "|" in custom_id:
                parts = str(custom_id).split("|")
                if len(parts) >= 3:
                    user_id, plan_id, billing_period = parts[0], parts[1], parts[2]

            tx = None
            if resource_id:
                tx = await db.payment_transactions.find_one(
                    {
                        "$or": [
                            {"session_id": resource_id},
                            {"paypal_capture_id": resource_id},
                            {"payment_id": resource_id},
                        ]
                    },
                    {"_id": 0},
                )

            if not tx and custom_id:
                tx = await db.payment_transactions.find_one(
                    {"session_id": resource.get("billing_agreement_id", "")},
                    {"_id": 0},
                )

            if tx:
                user_id = tx.get("user_id", user_id)
                plan_id = tx.get("plan_id", plan_id)
                billing_period = tx.get("billing_period", billing_period)

            if not user_id:
                logger.warning("PayPal webhook: could not resolve user for event=%s resource=%s", event_type, resource_id)
            else:
                plan = await get_subscription_plan_from_gps(plan_id)
                plan_name = plan["name"] if plan else plan_id
                amount = 0
                if plan:
                    amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]

                if event_type == "BILLING.SUBSCRIPTION.EXPIRED":
                    await dispatch_subscription_expiry_notification(
                        user_id,
                        source_provider="paypal",
                        reason="expired",
                        plan_name_override=plan_name,
                        transaction_filter={
                            "$or": [
                                {"session_id": resource_id},
                                {"paypal_capture_id": resource_id},
                                {"payment_id": resource_id},
                            ]
                        } if resource_id else None,
                    )
                elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
                    title, message, notif_type = _build_provider_failure_copy("PayPal", "cancelled", plan_name)
                    metadata = {"plan_id": plan_id, "subscription_id": resource_id, "provider": "paypal"}
                    await db.notifications.insert_one(
                        {
                            "id": f"notif_{uuid.uuid4().hex[:12]}",
                            "user_id": user_id,
                            "type": notif_type,
                            "title": title,
                            "message": message,
                            "read": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "metadata": metadata,
                        }
                    )
                else:
                    failure_state = "failed" if event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED" else "refunded"
                    title, message, notif_type = _build_provider_failure_copy("PayPal", failure_state, plan_name)
                    metadata = {"plan_id": plan_id, "amount": amount, "order_id": resource_id, "provider": "paypal"}
                    await db.notifications.insert_one(
                        {
                            "id": f"notif_{uuid.uuid4().hex[:12]}",
                            "user_id": user_id,
                            "type": notif_type,
                            "title": title,
                            "message": message,
                            "read": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "metadata": metadata,
                        }
                    )

        # ── PAYMENT.CAPTURE.DENIED / REFUNDED ──
        elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED"):
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id", "")
            new_status = "refunded" if "REFUNDED" in event_type else "failed"

            if order_id:
                await db.payment_transactions.update_one(
                    {"session_id": order_id},
                    {
                        "$set": {
                            "payment_status": new_status,
                            "webhook_received_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
                logger.info(f"PayPal webhook: transaction {order_id} marked {new_status}")

                # Send failure notification
                tx = await db.payment_transactions.find_one({"session_id": order_id}, {"_id": 0})
                if tx and tx.get("user_id"):
                    user_id = tx["user_id"]
                    plan_id = tx.get("plan_id", "basic")
                    plan = await get_subscription_plan_from_gps(plan_id)
                    plan_name = plan["name"] if plan else plan_id
                    amount = 0
                    if plan:
                        bp = tx.get("billing_period", "monthly")
                        amount = plan["monthly_price"] if bp == "monthly" else plan["yearly_price"]

                    await db.notifications.insert_one(
                        {
                            "id": f"notif_{uuid.uuid4().hex[:12]}",
                            "user_id": user_id,
                            "type": "payment_failed",
                            "title": _build_provider_failure_copy("PayPal", new_status, plan_name)[0],
                            "message": _build_provider_failure_copy("PayPal", new_status, plan_name)[1],
                            "read": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "metadata": {"plan_id": plan_id, "amount": amount, "order_id": order_id},
                        }
                    )

                    # Send refund-specific email if refunded
                    if new_status == "refunded" and is_email_configured():
                        try:
                            user_doc_ref = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                            if user_doc_ref and user_doc_ref.get("email"):
                                from utils.email_service import send_catalog_template
                                await send_catalog_template(
                                    recipient_email=user_doc_ref["email"],
                                    template_key="refund_notification",
                                    recipient_name=user_doc_ref.get("name", ""),
                                    user_name=user_doc_ref.get("name", "there"),
                                    amount=f"${amount:.2f}" if isinstance(amount, (int, float)) else str(amount),
                                    plan_name=plan_name,
                                    refund_reason="PayPal refund processed",
                                    refund_id=order_id,
                                )
                        except Exception as e:
                            logger.warning(f"Refund email failed: {e}")

                    if is_email_configured():
                        try:
                            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                            if user_doc and user_doc.get("email"):
                                bp = tx.get("billing_period", "monthly")
                                currency = tx.get("currency", "USD").upper()
                                amount_local = tx.get("amount_local", 0)
                                recovery_dispatch = await _send_user_payment_failure_recovery_email(
                                    user_id=user_id,
                                    user_email=user_doc["email"],
                                    user_name=user_doc.get("name", ""),
                                    plan_id=plan_id,
                                    plan_name=plan_name,
                                    billing_period=bp,
                                    payment_method="paypal",
                                    amount_usd=amount,
                                    currency=currency,
                                    amount_local=amount_local,
                                    session_id=order_id,
                                )
                                if not recovery_dispatch.get("sent") and recovery_dispatch.get("reason") == "daily_throttled":
                                    logger.info(
                                        "PayPal failure recovery email throttled for user=%s (last_email_at=%s)",
                                        user_id,
                                        recovery_dispatch.get("last_email_at"),
                                    )
                        except Exception as e:
                            logger.error(f"PayPal failure recovery email error: {e}")

                    try:
                        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
                        await _send_admin_payment_failure_alert(
                            customer_email=(user_doc or {}).get("email", ""),
                            plan_name=plan_name,
                            payment_method="paypal",
                            reason=new_status,
                            amount=amount,
                            amount_local=tx.get("amount_local", 0),
                            currency=tx.get("currency", "USD").upper(),
                            reference_id=order_id,
                        )
                    except Exception as e:
                        logger.warning(f"PayPal admin failure alert error: {e}")

        # ── CHECKOUT.ORDER.APPROVED / COMPLETED ──
        elif event_type in ("CHECKOUT.ORDER.APPROVED", "CHECKOUT.ORDER.COMPLETED"):
            order_id = resource.get("id", "")
            logger.info(f"PayPal webhook: order {order_id} {event_type}")

        return JSONResponse({"received": True, "event_type": event_type}, status_code=200)

    except Exception as exc:
        logger.error(f"PayPal webhook internal error: {exc}", exc_info=True)
        return JSONResponse({"received": True, "error": "internal"}, status_code=200)


# ── Admin: PayPal production-behavior E2E simulator ──
# Shared orchestration lives in payments_simulation_core.run_provider_payment_simulation.

class PayPalSimulationRequest(ProviderSimulationRequest):
    plan: str = "basic"
    city: str = "Plummers Landing"
    state_code: str = "KY"
    postal_code: str = "41081"


@router.post("/admin/payments/simulate-paypal-production-e2e")
async def simulate_paypal_production_e2e(body: PayPalSimulationRequest, request: Request):
    admin = await get_current_user(request)
    if not admin or not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await run_provider_payment_simulation(
        body,
        provider="paypal",
        fee_provider="paypal",
        tx_payment_method="paypal_js",
        payment_method_label="PayPal",
        ticket_prefix="PP",
        tx_prefix="sim_paypal",
        ledger_event_type="provider_capture_completed",
        provider_display="PayPal",
        get_plan=get_subscription_plan_from_gps,
        send_payment_notification=_send_payment_notification,
        queue_payment_notification_recovery=_queue_payment_notification_recovery,
        build_payment_record_from_tx=_build_payment_record_from_tx,
        failure_copy=_build_provider_failure_copy,
        append_transition=None,
        extra_user_fields={"last_payment_method": "paypal_js"},
    )
