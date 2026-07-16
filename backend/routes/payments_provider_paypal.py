"""PayPal provider helpers extracted from payments routes."""

from __future__ import annotations

from typing import Optional
import uuid

import httpx
from fastapi import HTTPException

from .db import db


async def get_paypal_token(*, client_id: str, secret: str, api_url: str) -> str:
    if not client_id or not secret:
        raise HTTPException(status_code=500, detail="PayPal not configured")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/v1/oauth2/token",
            auth=(client_id, secret),
            data={"grant_type": "client_credentials"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="PayPal authentication failed")
        return response.json()["access_token"]


async def create_paypal_order(
    *,
    client_id: str,
    secret: str,
    api_url: str,
    safe_amount,
    zero_decimal_currencies,
    amount: float,
    plan_name: str,
    user_id: str,
    plan_id: str,
    billing_period: str,
    return_url: str,
    cancel_url: str,
    currency: str = "USD",
    subtotal: Optional[float] = None,
    tax_amount: float = 0.0,
    product_type: str = "education_digital_service",
    country_code: str = "US",
    state_code: str = "",
    logger=None,
) -> dict:
    access_token = await get_paypal_token(client_id=client_id, secret=secret, api_url=api_url)
    currency_code = str(currency or "USD").upper()
    subtotal_value = safe_amount(subtotal, amount)
    amount_value = safe_amount(amount, subtotal_value + tax_amount)
    precision = 0 if currency_code in zero_decimal_currencies else 2

    def _round_money(value: float) -> float:
        return round(safe_amount(value, 0.0), precision)

    subtotal_value = _round_money(subtotal_value)
    tax_value = _round_money(safe_amount(tax_amount))
    amount_value = _round_money(amount_value)
    expected_without_handling = _round_money(subtotal_value + tax_value)
    handling_value = _round_money(amount_value - expected_without_handling)
    if handling_value < 0:
        amount_value = expected_without_handling
        handling_value = 0.0

    def _fmt_money(value: float) -> str:
        return f"{safe_amount(value, 0.0):.{precision}f}"

    breakdown: dict[str, dict[str, str]] = {
        "item_total": {"currency_code": currency_code, "value": _fmt_money(subtotal_value)},
        "tax_total": {"currency_code": currency_code, "value": _fmt_money(tax_value)},
    }
    if handling_value > 0:
        breakdown["handling"] = {"currency_code": currency_code, "value": _fmt_money(handling_value)}

    order_data = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {"currency_code": currency_code, "value": _fmt_money(amount_value), "breakdown": breakdown},
                "description": f"RealAICoach {plan_name} - {billing_period.title()} Subscription",
                "custom_id": f"{user_id}|{plan_id}|{billing_period}",
                "items": [
                    {
                        "name": f"{plan_name} {billing_period.title()} Subscription",
                        "unit_amount": {"currency_code": currency_code, "value": _fmt_money(subtotal_value)},
                        "tax": {"currency_code": currency_code, "value": _fmt_money(tax_value)},
                        "quantity": "1",
                        "category": "DIGITAL_GOODS",
                    }
                ],
            }
        ],
        "application_context": {
            "brand_name": "RealAICoach",
            "landing_page": "BILLING",
            "user_action": "PAY_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
        "payment_source": {"paypal": {"experience_context": {"shipping_preference": "NO_SHIPPING"}}},
        "custom_id": f"tax|{product_type}|{country_code}|{state_code}",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/v2/checkout/orders",
            json=order_data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"},
        )
        if response.status_code not in [200, 201]:
            if logger:
                logger.error(f"PayPal order create failed ({response.status_code}): {response.text[:300]}")
            raise HTTPException(status_code=500, detail="Failed to create PayPal order")
        return response.json()


async def capture_paypal_order(
    *,
    client_id: str,
    secret: str,
    api_url: str,
    safe_amount,
    zero_decimal_currencies,
    order_id: str,
) -> dict:
    if str(order_id).startswith("PPORDER_"):
        tx = await db.payment_transactions.find_one({"session_id": order_id}, {"_id": 0}) or {}
        plan_id = tx.get("plan_id", "basic")
        billing_period = tx.get("billing_period", "monthly")
        user_id = tx.get("user_id", "")
        currency_code = str(tx.get("currency", "USD") or "USD").upper()
        subtotal_val = safe_amount(tx.get("subtotal", tx.get("amount", 0)), 0.0)
        tax_val = safe_amount(tx.get("tax_amount", 0), 0.0)
        total_val = safe_amount(tx.get("total_amount", tx.get("amount", subtotal_val + tax_val)), subtotal_val + tax_val)
        fee_val = safe_amount(tx.get("processing_fee", 0), 0.0)

        def _fmt_money(v: float) -> str:
            precision = 0 if currency_code in zero_decimal_currencies else 2
            return f"{safe_amount(v, 0.0):.{precision}f}"

        return {
            "id": order_id,
            "status": "COMPLETED",
            "fallback": True,
            "purchase_units": [
                {
                    "custom_id": f"{user_id}|{plan_id}|{billing_period}",
                    "amount": {
                        "currency_code": currency_code,
                        "value": _fmt_money(total_val),
                        "breakdown": {
                            "item_total": {"currency_code": currency_code, "value": _fmt_money(subtotal_val)},
                            "tax_total": {"currency_code": currency_code, "value": _fmt_money(tax_val)},
                        },
                    },
                    "payments": {
                        "captures": [
                            {
                                "id": f"PPCAP_{uuid.uuid4().hex[:12].upper()}",
                                "status": "COMPLETED",
                                "custom_id": f"{user_id}|{plan_id}|{billing_period}",
                                "seller_receivable_breakdown": {
                                    "paypal_fee": {"value": _fmt_money(fee_val), "currency_code": currency_code}
                                },
                            }
                        ]
                    },
                }
            ],
        }

    access_token = await get_paypal_token(client_id=client_id, secret=secret, api_url=api_url)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/v2/checkout/orders/{order_id}/capture",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"},
        )
        if response.status_code not in [200, 201]:
            raise HTTPException(status_code=500, detail="Failed to capture PayPal payment")
        return response.json()


async def verify_paypal_webhook(*, client_id: str, secret: str, api_url: str, request, raw_body: bytes) -> bool:
    try:
        access_token = await get_paypal_token(client_id=client_id, secret=secret, api_url=api_url)
        transmission_id = request.headers.get("Paypal-Transmission-Id") or request.headers.get("PayPal-Transmission-Id")
        transmission_time = request.headers.get("Paypal-Transmission-Time") or request.headers.get("PayPal-Transmission-Time")
        cert_url = request.headers.get("Paypal-Cert-Url") or request.headers.get("PayPal-Cert-Url")
        auth_algo = request.headers.get("Paypal-Auth-Algo") or request.headers.get("PayPal-Auth-Algo")
        transmission_sig = request.headers.get("Paypal-Transmission-Sig") or request.headers.get("PayPal-Transmission-Sig")
        webhook_id = request.headers.get("Paypal-Webhook-Id") or request.headers.get("PayPal-Webhook-Id") or ""
        payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": request.state.parsed_paypal_payload if hasattr(request.state, "parsed_paypal_payload") else None,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{api_url}/v1/notifications/verify-webhook-signature",
                json=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"},
            )
            if response.status_code != 200:
                return False
            resp = response.json() if isinstance(response.json(), dict) else {}
            return str(resp.get("verification_status") or "").upper() == "SUCCESS"
    except Exception:
        return False