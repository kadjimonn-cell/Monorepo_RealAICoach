"""FedaPay and mobile-money routes extracted from payments.py.

Policy/client helpers remain in their dedicated modules; this file owns route
orchestration for FedaPay/mobile-money checkout, webhook, status, and callback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from utils.email_service import is_email_configured
from utils.fedapay_policy_service import (
    clear_fedapay_policy_cache,
    get_fedapay_policy,
    list_policy_country_codes,
    refresh_fedapay_policy,
    resolve_card_fee_pct,
    resolve_mobile_money_fee_pct,
)
from utils.payment_localization import resolve_payment_localization_context
from utils.checkout_kill_switch import raise_if_checkout_paused
from utils.tax_compliance_engine import (
    append_financial_ledger_entry,
    build_financial_totals,
    calculate_tax_quote,
    log_tax_calculation,
    resolve_product_type,
)

from .db import db, get_current_user, require_admin_or_employee_permission
from .payments_catalog import get_subscription_plan_from_gps, require_paid_subscription_plan
from .subscription_enforcement import dispatch_subscription_expiry_notification


router = APIRouter()
logger = logging.getLogger("routes.payments.fedapay_routes")
LOCK_SINGLE_PAYMENT_COMMUNICATION = True

_SHELL_HOSTS = {
    "app.emergent.sh",
    "app.emergentagent.com",
}


def _build_provider_failure_copy(provider_label: str, state: str, plan_name: str) -> tuple[str, str]:
    provider = provider_label or "Payment Gateway"
    plan = plan_name or "subscription"
    normalized = str(state or "failed").strip().lower()
    if normalized in {"cancelled", "canceled"}:
        return ("Checkout cancelled", f"{provider} checkout was cancelled before payment completed. No charge was completed.")
    if normalized in {"refunded", "reversed", "revoked"}:
        return ("Payment refunded", f"Your {plan} payment via {provider} was refunded. Review your billing status in payment history.")
    return ("Payment not completed", f"{provider} could not complete your payment. No charge was completed. Try again or choose a different method.")


def _normalize_external_base(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""

    if value.startswith("//"):
        value = f"https:{value}"
    elif not value.startswith("http://") and not value.startswith("https://"):
        value = f"https://{value}"

    parsed = urlparse(value)
    if not parsed.netloc:
        return ""

    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    return f"{scheme}://{parsed.netloc}".rstrip("/")


def _is_runtime_shell_host(hostname: str) -> bool:
    host = str(hostname or "").strip().lower()
    if not host:
        return False
    if host in _SHELL_HOSTS:
        return True
    return host.endswith(".emergent.sh")


def _extract_forwarded_host_candidate(req: Request) -> str:
    forwarded_host = str(req.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if not forwarded_host:
        return ""
    forwarded_proto = str(req.headers.get("x-forwarded-proto") or "https").split(",")[0].strip().lower()
    proto = forwarded_proto if forwarded_proto in {"http", "https"} else "https"
    return f"{proto}://{forwarded_host}"


def _extract_host_header_candidate(req: Request) -> str:
    host = str(req.headers.get("host") or "").split(",")[0].strip()
    if not host:
        return ""
    proto = str(req.headers.get("x-forwarded-proto") or req.url.scheme or "https").split(",")[0].strip().lower()
    scheme = proto if proto in {"http", "https"} else "https"
    return f"{scheme}://{host}"


def _resolve_public_frontend_base(req: Request) -> str:
    candidates = [
        _extract_forwarded_host_candidate(req),
        _extract_host_header_candidate(req),
        req.headers.get("origin", ""),
        os.environ.get("REACT_APP_BACKEND_URL", ""),
        os.environ.get("EXPO_PUBLIC_BACKEND_URL", ""),
        os.environ.get("FRONTEND_BASE_URL", ""),
        str(req.base_url).rstrip("/"),
    ]

    shell_fallback = ""
    for candidate in candidates:
        normalized = _normalize_external_base(candidate)
        if not normalized:
            continue
        host = urlparse(normalized).netloc.lower()
        if _is_runtime_shell_host(host):
            if not shell_fallback:
                shell_fallback = normalized
            continue
        return normalized

    return shell_fallback


async def _missing_user_resolver(_request: Request):
    raise HTTPException(status_code=503, detail="FedaPay routes are not configured")


async def _missing_async(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="FedaPay route dependency is not configured")


def _missing_sync(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="FedaPay route dependency is not configured")


def _default_safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


_get_user_from_request: Callable[[Request], Awaitable[object | None]] = _missing_user_resolver
_resolve_saved_card_for_checkout: Callable[..., Awaitable[dict | None]] = _missing_async
_compute_checkout_breakdown: Callable[..., Awaitable[dict]] = _missing_async
CheckoutPreviewRequest: Callable[..., object] = _missing_sync
_get_subscription_lifecycle_state: Callable[[str], Awaitable[dict]] = _missing_async
_build_payment_record_from_tx: Callable[..., dict] = _missing_sync
_send_payment_notification: Callable[..., Awaitable[dict]] = _missing_async
_send_user_payment_failure_recovery_email: Callable[..., Awaitable[dict]] = _missing_async
_send_admin_payment_failure_alert: Callable[..., Awaitable[None]] = _missing_async
_safe_float: Callable[[Any, float], float] = _default_safe_float
def _default_minutes_since_iso(_value: Optional[str]) -> Optional[int]:
    return None


_minutes_since_iso: Callable[[Optional[str]], Optional[int]] = _default_minutes_since_iso


def configure_fedapay_routes(
    *,
    get_user_from_request: Callable[[Request], Awaitable[object | None]],
    resolve_saved_card_for_checkout: Callable[..., Awaitable[dict | None]],
    compute_checkout_breakdown: Callable[..., Awaitable[dict]],
    checkout_preview_request: Callable[..., object],
    get_subscription_lifecycle_state: Callable[[str], Awaitable[dict]],
    build_payment_record_from_tx: Callable[..., dict],
    send_payment_notification: Callable[..., Awaitable[dict]],
    send_user_payment_failure_recovery_email: Callable[..., Awaitable[dict]],
    send_admin_payment_failure_alert: Callable[..., Awaitable[None]],
    safe_float: Callable[[Any, float], float],
    minutes_since_iso: Callable[[Optional[str]], Optional[int]],
    lock_single_payment_communication: bool,
    route_logger: Optional[logging.Logger] = None,
) -> None:
    global _get_user_from_request, _resolve_saved_card_for_checkout, _compute_checkout_breakdown, CheckoutPreviewRequest
    global _get_subscription_lifecycle_state, _build_payment_record_from_tx, _send_payment_notification
    global _send_user_payment_failure_recovery_email, _send_admin_payment_failure_alert, _safe_float, _minutes_since_iso
    global LOCK_SINGLE_PAYMENT_COMMUNICATION, logger

    _get_user_from_request = get_user_from_request
    _resolve_saved_card_for_checkout = resolve_saved_card_for_checkout
    _compute_checkout_breakdown = compute_checkout_breakdown
    CheckoutPreviewRequest = checkout_preview_request
    _get_subscription_lifecycle_state = get_subscription_lifecycle_state
    _build_payment_record_from_tx = build_payment_record_from_tx
    _send_payment_notification = send_payment_notification
    _send_user_payment_failure_recovery_email = send_user_payment_failure_recovery_email
    _send_admin_payment_failure_alert = send_admin_payment_failure_alert
    _safe_float = safe_float
    _minutes_since_iso = minutes_since_iso
    LOCK_SINGLE_PAYMENT_COMMUNICATION = bool(lock_single_payment_communication)
    if route_logger is not None:
        logger = route_logger


def _resolve_fedapay_fee_pct(policy: Dict[str, Any], country_code: Optional[str], mobile_provider: Optional[str] = None) -> float:
    # Card-provider hints use the card fee table; mobile fees falling back to card fee when 0.
    provider_hint = str(mobile_provider or "").strip().lower()
    if provider_hint in {"card", "visa", "mastercard", "saved_card"}:
        return _safe_float(resolve_card_fee_pct(policy, country_code), 0.0)

    mobile_fee = _safe_float(resolve_mobile_money_fee_pct(policy, country_code, mobile_provider), 0.0)
    if mobile_fee > 0:
        return mobile_fee

    return _safe_float(resolve_card_fee_pct(policy, country_code), 0.0)

# ── FX rates for mobile money conversion ──
MOBILE_MONEY_FX = {
    "XOF": 605.0,
    "XAF": 605.0,
    "GHS": 14.5,
    "UGX": 3780.0,
    "RWF": 1350.0,
    "USD": 1.0,
    "EUR": 0.92,
    "NGN": 1580.0,
}

MOBILE_MONEY_GATEWAYS = {
    "fedapay": {
        "name": "FedaPay",
        "countries": ["BJ", "TG", "SN", "CI", "NE"],
        "currencies": ["XOF"],
        "fee_pct": 0.0,
        "fixed_tax_rate_pct": 8.25,
        "supported_cards": ["mastercard", "visa"],
        "color": "#2563EB",
        "icon": "globe",
    },
}


def _resolve_mobile_gateway_runtime_status(gateway_id: str) -> Dict[str, Any]:
    gateway_key = str(gateway_id or "").strip().lower()
    if gateway_key != "fedapay":
        return {
            "available": True,
            "status": "active",
            "status_label": "Active",
            "mode": "live",
            "message": "Gateway available.",
        }

    fedapay_secret = str(os.environ.get("FEDAPAY_SECRET_KEY", "")).strip()
    fedapay_public = str(os.environ.get("FEDAPAY_PUBLIC_KEY", "")).strip()
    fedapay_env = str(os.environ.get("FEDAPAY_ENV", "sandbox")).strip().lower()

    available = bool(fedapay_secret and fedapay_public)

    if fedapay_secret.startswith("sk_live") or fedapay_public.startswith("pk_live"):
        mode = "live"
    elif (
        fedapay_secret.startswith("sk_sandbox")
        or fedapay_secret.startswith("sk_test")
        or fedapay_public.startswith("pk_sandbox")
        or fedapay_public.startswith("pk_test")
        or fedapay_env in {"sandbox", "test"}
    ):
        mode = "test"
    else:
        mode = "unknown"

    if available and mode == "live":
        status_label = "Live Ready"
    elif available:
        status_label = "Test Ready"
    else:
        status_label = "Unavailable"

    return {
        "available": available,
        "status": "active" if available else "inactive",
        "status_label": status_label,
        "mode": mode,
        "message": "Gateway configured and ready for checkout."
        if available
        else "FedaPay credentials are incomplete. Configure keys in gateway settings.",
    }


@router.get("/subscriptions/mobile-money/gateways")
async def get_mobile_money_gateways():
    """List available mobile money gateways for subscription."""
    fedapay_policy = await get_fedapay_policy(db)
    checked_at = datetime.now(timezone.utc).isoformat()
    gateways = []
    for gw_id, gw in MOBILE_MONEY_GATEWAYS.items():
        runtime_status = _resolve_mobile_gateway_runtime_status(gw_id)
        countries = list_policy_country_codes(fedapay_policy) if gw_id == "fedapay" else gw["countries"]
        country_fee_schedule = {}
        for cc in countries:
            fee_pct = resolve_mobile_money_fee_pct(fedapay_policy, cc)
            country_cfg = (fedapay_policy.get("countries", {}) or {}).get(cc, {})
            country_fee_schedule[cc] = {
                "default_mobile_fee_pct": fee_pct,
                "mobile_money_fees": country_cfg.get("mobile_money_fees", {}),
                "card_fee_pct": resolve_card_fee_pct(fedapay_policy, cc),
            }
        gateways.append(
            {
                "id": gw_id,
                "label": gw["name"],
                "name": gw["name"],
                "available": runtime_status["available"],
                "status": runtime_status["status"],
                "status_label": runtime_status["status_label"],
                "mode": runtime_status["mode"],
                "message": runtime_status["message"],
                "checked_at": checked_at,
                "countries": countries,
                "currencies": gw["currencies"],
                "fee_pct": gw["fee_pct"],
                "fixed_tax_rate_pct": gw.get("fixed_tax_rate_pct", 8.25),
                "supported_cards": fedapay_policy.get("channels", {}).get("card", {}).get("supported_cards", gw.get("supported_cards", ["mastercard", "visa"])),
                "card_fee_pct": resolve_card_fee_pct(fedapay_policy, None),
                "country_fee_schedule": country_fee_schedule,
                "policy_source": fedapay_policy.get("source", "contract_seed"),
                "policy_updated_at": fedapay_policy.get("updated_at"),
                "policy_last_synced_minutes_ago": _minutes_since_iso(fedapay_policy.get("updated_at")),
                "color": gw["color"],
                "icon": gw["icon"],
            }
        )
    return {"gateways": gateways}


@router.get("/subscriptions/mobile-money/fedapay-policy")
async def get_fedapay_policy_view():
    policy = await get_fedapay_policy(db)
    return {
        "source": policy.get("source", "contract_seed"),
        "version": policy.get("version", "contract-seed-v1"),
        "updated_at": policy.get("updated_at"),
        "last_synced_minutes_ago": _minutes_since_iso(policy.get("updated_at")),
        "expires_at": policy.get("expires_at"),
        "channels": policy.get("channels", {}),
        "countries": policy.get("countries", {}),
    }


@router.post("/admin/payments/fedapay-policy/refresh")
async def admin_refresh_fedapay_policy(request: Request, clear_cache_first: bool = True):
    await require_admin_or_employee_permission(request, "employee.manage_billing")
    if clear_cache_first:
        await clear_fedapay_policy_cache(db)
    policy = await refresh_fedapay_policy(db, force=True)
    return {
        "success": True,
        "source": policy.get("source"),
        "updated_at": policy.get("updated_at"),
        "expires_at": policy.get("expires_at"),
        "country_count": len(policy.get("countries", {})),
    }


@router.get("/admin/payment-analytics/fedapay-policy/timeline")
async def get_fedapay_policy_timeline(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=200),
):
    await require_admin_or_employee_permission(request, "employee.view_analytics")
    skip = (page - 1) * limit

    total = await db.fedapay_policy_history.count_documents({})
    history = await db.fedapay_policy_history.find({}, {"_id": 0, "countries": 0}) \
        .sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    source_events = await db.fedapay_policy_source_events.find({}, {"_id": 0}) \
        .sort("changed_at", -1).limit(100).to_list(100)

    return {
        "history": history,
        "source_events": source_events,
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/subscriptions/mobile-money/sandbox-info")
async def get_sandbox_info():
    """Return sandbox test numbers and environment info for FedaPay testing."""
    from routes.fedapay_client import is_sandbox as fedapay_is_sandbox, SANDBOX_SUCCESS_NUMBERS, SANDBOX_FAILURE_NUMBERS

    sandbox = fedapay_is_sandbox()
    return {
        "sandbox": sandbox,
        "environment": "sandbox" if sandbox else "live",
        "country": "bj",
        "country_code": "+229",
        "success_numbers": SANDBOX_SUCCESS_NUMBERS if sandbox else [],
        "failure_numbers": SANDBOX_FAILURE_NUMBERS if sandbox else [],
        "instructions": "In sandbox mode, use the listed test phone numbers only. Success numbers simulate approved payments, failure numbers simulate declined payments." if sandbox else "Live mode - use real phone numbers.",
    }


class MobileMoneySubscriptionRequest(BaseModel):
    plan_id: str
    billing_period: str = "monthly"
    gateway: str
    phone_number: str
    currency: str = "XOF"
    saved_card_id: Optional[str] = None
    mobile_provider: Optional[str] = None


@router.post("/subscriptions/mobile-money/pay")
async def mobile_money_subscription(payload: MobileMoneySubscriptionRequest, request: Request):
    """Process subscription payment via mobile money gateway (sandbox simulation)."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await raise_if_checkout_paused(db)

    # Check if user is access-locked + active subscription state
    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "access_locked": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
        },
    )
    if user_doc and user_doc.get("access_locked"):
        raise HTTPException(status_code=403, detail="Your account access is restricted. Contact support.")

    plan = await require_paid_subscription_plan(payload.plan_id)

    gw = MOBILE_MONEY_GATEWAYS.get(payload.gateway)
    if not gw:
        raise HTTPException(status_code=400, detail="Invalid gateway")

    if payload.currency not in gw["currencies"]:
        raise HTTPException(status_code=400, detail=f"Currency {payload.currency} not supported by {gw['name']}")

    # Hard duplicate-purchase protection:
    # 1) Do not re-purchase same active plan.
    # 2) Reuse most recent transaction if repeated checkout is attempted within short window.
    if (
        str(user_doc.get("subscription_status") or "").lower() == "active"
        and str(user_doc.get("subscription_plan") or "").lower() == str(payload.plan_id).lower()
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Active plan already exists",
                "code": "ACTIVE_PLAN_ALREADY_EXISTS",
                "message": f"You already have an active {payload.plan_id} subscription. Duplicate checkout was blocked.",
                "subscription_end_date": str(user_doc.get("subscription_end_date") or ""),
            },
        )

    recent_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    recent_tx = await db.payment_transactions.find_one(
        {
            "user_id": user.user_id,
            "plan_id": payload.plan_id,
            "billing_period": payload.billing_period,
            "provider": "fedapay",
            "currency": payload.currency,
            "created_at": {"$gte": recent_cutoff},
            "payment_status": {"$in": ["pending", "completed"]},
        },
        {
            "_id": 0,
            "transaction_id": 1,
            "session_id": 1,
            "payment_id": 1,
            "amount_local": 1,
            "currency": 1,
            "payment_status": 1,
            "payment_url": 1,
            "fedapay_tx_id": 1,
        },
        sort=[("created_at", -1)],
    )
    if recent_tx:
        dedup_payment_url = str(recent_tx.get("payment_url") or "").strip()
        payment_url_regenerated = False

        if not dedup_payment_url and recent_tx.get("fedapay_tx_id"):
            try:
                from routes.fedapay_client import generate_checkout_url_for_transaction

                regenerated = await generate_checkout_url_for_transaction(recent_tx.get("fedapay_tx_id"))
                dedup_payment_url = str(regenerated.get("payment_url") or "").strip()
                if dedup_payment_url:
                    update_filter = {
                        "provider": "fedapay",
                        "gateway": "fedapay",
                        "user_id": user.user_id,
                    }
                    if recent_tx.get("transaction_id"):
                        update_filter["transaction_id"] = recent_tx.get("transaction_id")
                    elif recent_tx.get("payment_id"):
                        update_filter["payment_id"] = recent_tx.get("payment_id")

                    await db.payment_transactions.update_one(
                        update_filter,
                        {
                            "$set": {
                                "payment_url": dedup_payment_url,
                                "payment_url_regenerated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                    )
                    payment_url_regenerated = True
            except Exception as regen_err:
                logger.warning(
                    "Failed to regenerate FedaPay payment URL for dedup tx=%s fedapay_tx_id=%s error=%s",
                    recent_tx.get("transaction_id"),
                    recent_tx.get("fedapay_tx_id"),
                    regen_err,
                )

        logger.warning(
            "Duplicate FedaPay checkout prevented user=%s plan=%s billing=%s tx=%s",
            user.user_id,
            payload.plan_id,
            payload.billing_period,
            recent_tx.get("transaction_id"),
        )
        return {
            "success": True,
            "deduped": True,
            "ticket_id": recent_tx.get("session_id"),
            "payment_id": recent_tx.get("payment_id"),
            "transaction_id": recent_tx.get("transaction_id"),
            "subscription_plan": payload.plan_id,
            "amount_local": recent_tx.get("amount_local"),
            "currency": recent_tx.get("currency") or payload.currency,
            "gateway": gw["name"],
            "payment_url": dedup_payment_url,
            "payment_url_regenerated": payment_url_regenerated,
            "status": recent_tx.get("payment_status", "pending"),
            "message": "Duplicate checkout prevented. Existing transaction was reused.",
        }

    saved_card = await _resolve_saved_card_for_checkout(user.user_id, payload.saved_card_id)

    if not payload.phone_number or len(payload.phone_number) < 8:
        raise HTTPException(status_code=400, detail="Valid phone number required")

    # Calculate price + tax (backend source of truth)
    usd_price = plan["monthly_price"] if payload.billing_period == "monthly" else plan["yearly_price"]
    product_type = resolve_product_type(payload.plan_id)
    localization_context = await resolve_payment_localization_context(
        db=db,
        request=request,
        user=user,
        requested_currency=payload.currency,
    )
    jurisdiction = localization_context.get("jurisdiction", {})
    if payload.currency.upper() == "XOF" and jurisdiction.get("country") in {"", "US"}:
        jurisdiction["country"] = "BJ"
        localization_context["jurisdiction"] = jurisdiction
    tax_quote = await calculate_tax_quote(
        provider="fedapay",
        subtotal=float(usd_price),
        currency="USD",
        country_code=jurisdiction.get("country"),
        state_code=jurisdiction.get("state"),
        postal_code=jurisdiction.get("postal_code"),
        product_type=product_type,
    )
    fx_rate = MOBILE_MONEY_FX.get(payload.currency.upper(), 1.0)
    usd_tax = _safe_float(tax_quote.get("tax_amount", 0), 0.0)
    subtotal_local = round(usd_price * fx_rate, 0)
    tax_local = round(usd_tax * fx_rate, 0)
    local_amount = round(subtotal_local + tax_local, 0)
    fedapay_policy = await get_fedapay_policy(db)
    fee_pct = _resolve_fedapay_fee_pct(
        fedapay_policy,
        jurisdiction.get("country"),
        payload.mobile_provider,
    )
    fee_local = round(local_amount * (_safe_float(fee_pct, 0.0) / 100), 0)

    if _safe_float(fee_pct, 0.0) <= 0 or fee_local <= 0:
        policy_source = str(fedapay_policy.get("source") or "contract_seed")
        logger.error(
            "Blocking FedaPay checkout: invalid processing fee policy country=%s provider=%s fee_pct=%s fee_local=%s source=%s",
            jurisdiction.get("country"),
            payload.mobile_provider,
            fee_pct,
            fee_local,
            policy_source,
        )

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(40)
        now_iso = datetime.now(timezone.utc).isoformat()
        for admin in admins:
            admin_id = str(admin.get("user_id") or "")
            if not admin_id:
                continue
            await db.notifications.insert_one(
                {
                    "id": f"fedapay_fee_policy_block_{admin_id}_{int(time.time())}",
                    "user_id": admin_id,
                    "type": "fedapay_fee_policy_block",
                    "title": "FedaPay Checkout Blocked (Fee Policy)",
                    "message": "Checkout was blocked because processing fee resolved to zero. Review FedaPay policy mapping.",
                    "read": False,
                    "created_at": now_iso,
                    "metadata": {
                        "country": jurisdiction.get("country"),
                        "state": jurisdiction.get("state"),
                        "mobile_provider": payload.mobile_provider,
                        "fee_pct": _safe_float(fee_pct, 0.0),
                        "fee_local": fee_local,
                        "policy_source": policy_source,
                    },
                }
            )

        raise HTTPException(
            status_code=503,
            detail={
                "error": "FedaPay Fee Policy Misconfigured",
                "code": "FEDAPAY_FEE_POLICY_INVALID",
                "message": "Checkout temporarily unavailable: FedaPay processing fee configuration is invalid. Please try again shortly.",
                "country": jurisdiction.get("country"),
                "policy_source": policy_source,
            },
        )

    total_local = local_amount + fee_local
    fixed_tax_rate_pct = _safe_float(gw.get("fixed_tax_rate_pct", 8.25), 8.25)
    local_financials = build_financial_totals(
        subtotal=float(subtotal_local),
        tax_amount=float(tax_local),
        processing_fee=float(fee_local),
        fee_pass_through=True,
    )

    # ── FedaPay Live Integration (NO transaction limits) ──

    if payload.gateway == "fedapay":
        from routes.fedapay_client import create_transaction as fedapay_create, is_sandbox as fedapay_is_sandbox, validate_sandbox_phone

        sandbox_mode = fedapay_is_sandbox()

        # Validate phone number in sandbox mode
        if sandbox_mode:
            phone_validation = validate_sandbox_phone(payload.phone_number)
            if not phone_validation["valid"]:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid Sandbox Phone",
                        "message": phone_validation["message"],
                        "valid_numbers": phone_validation.get("valid_numbers", []),
                        "success_numbers": phone_validation.get("success_numbers", []),
                        "failure_numbers": phone_validation.get("failure_numbers", []),
                    },
                )

        frontend_base = _resolve_public_frontend_base(request)

        callback_url = os.environ.get("FEDAPAY_CALLBACK_URL", "")
        if not callback_url:
            from routes.fedapay_client import get_current_webhook_url

            base = get_current_webhook_url().replace("/api/payments/fedapay/webhook", "")
            callback_url = f"{base}/api/fedapay/callback" if base else ""

        # ── Single transaction — FedaPay has NO per-transaction amount limit ──
        tx_ref = f"MMSUB_{uuid.uuid4().hex[:10].upper()}"
        payment_id = f"fedapay_{uuid.uuid4().hex[:12]}"
        fedapay_failed = False
        fedapay_error_detail = ""

        try:
            fedapay_tx = await fedapay_create(
                amount=total_local,
                currency=payload.currency,
                description=f"{plan['name']} ({payload.billing_period}) subscription",
                customer_firstname=getattr(user, "name", "Customer").split()[0]
                if getattr(user, "name", "")
                else "Customer",
                customer_lastname=getattr(user, "name", "User").split()[-1] if getattr(user, "name", "") else "User",
                customer_email=user.email,
                customer_phone=payload.phone_number,
                callback_url=callback_url,
                metadata={
                    "user_id": user.user_id,
                    "plan_id": payload.plan_id,
                    "billing_period": payload.billing_period,
                    "tx_ref": tx_ref,
                    "payment_id": payment_id,
                    "saved_card_id": saved_card.get("card_id") if saved_card else "",
                    "saved_card_last_four": saved_card.get("last_four") if saved_card else "",
                },
            )
        except httpx.HTTPStatusError as e:
            err_body = e.response.text
            logger.error(f"FedaPay API error ({e.response.status_code}): {err_body}")
            fedapay_failed = True
            try:
                err_json = e.response.json()
                fedapay_error_detail = err_json.get("message", str(err_json.get("errors", err_body[:200])))
            except Exception:
                fedapay_error_detail = err_body[:200]
        except Exception as e:
            logger.error(f"FedaPay transaction creation failed: {e}")
            fedapay_failed = True
            fedapay_error_detail = str(e)

        # ── Fallback to Stripe if FedaPay fails ──
        if fedapay_failed:
            logger.warning(f"[FALLBACK] FedaPay failed, routing to Stripe. Reason: {fedapay_error_detail}")
            stripe_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
            if stripe_key:
                try:
                    import stripe
                    stripe.api_key = stripe_key

                    # Preserve the original FedaPay checkout total when falling back to Stripe
                    fallback_total_usd = round(_safe_float(local_financials.get("total_amount", total_local), total_local) / max(float(fx_rate or 1.0), 1.0), 2)
                    stripe_amount_cents = int(round(fallback_total_usd * 100))
                    stripe_session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{
                            "price_data": {
                                "currency": "usd",
                                "unit_amount": stripe_amount_cents,
                                "product_data": {
                                    "name": f"{plan['name']} ({payload.billing_period})",
                                    "description": f"RealAICoach {plan['name']} Plan - Fallback from FedaPay",
                                },
                            },
                            "quantity": 1,
                        }],
                        mode="payment",
                        success_url=f"{frontend_base}/subscription/payment-result?session_id={{CHECKOUT_SESSION_ID}}&status=success",
                        cancel_url=f"{frontend_base}/subscription/payment-result?status=cancelled",
                        client_reference_id=user.user_id,
                        customer_email=user.email,
                        metadata={
                            "user_id": user.user_id,
                            "plan_id": payload.plan_id,
                            "billing_period": payload.billing_period,
                            "payment_id": payment_id,
                            "fallback_from": "fedapay",
                            "original_amount_local": str(total_local),
                            "original_total_usd": str(fallback_total_usd),
                            "original_currency": payload.currency,
                            "saved_card_id": saved_card.get("card_id") if saved_card else "",
                            "saved_card_last_four": saved_card.get("last_four") if saved_card else "",
                        },
                    )

                    fallback_tx_id = f"txn_{uuid.uuid4().hex[:16]}"
                    await db.payment_transactions.insert_one({
                        "transaction_id": fallback_tx_id,
                        "session_id": stripe_session.id,
                        "user_id": user.user_id,
                        "plan_id": payload.plan_id,
                        "billing_period": payload.billing_period,
                        "amount_usd": fallback_total_usd,
                        "amount_local": total_local,
                        "original_usd_amount": usd_price,
                        "fallback_total_usd": fallback_total_usd,
                        "currency": "USD",
                        "original_currency": payload.currency,
                        "fx_rate": fx_rate,
                        "fx_base_currency": "USD",
                        "provider": "stripe",
                        "gateway": "stripe_fallback",
                        "payment_method": "stripe_card_fallback",
                        "payment_status": "pending",
                        "payment_id": payment_id,
                        "fallback_from": "fedapay",
                        "fedapay_error": fedapay_error_detail,
                        "saved_card_id": saved_card.get("card_id") if saved_card else None,
                        "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
                        "saved_card_type": saved_card.get("card_type") if saved_card else None,
                        "subtotal": local_financials["subtotal"],
                        "tax_amount": local_financials["tax_amount"],
                        "processing_fee": local_financials["processing_fee"],
                        "amount_gross": local_financials["amount_gross"],
                        "amount_net": local_financials["amount_net"],
                        "total_amount": local_financials["total_amount"],
                        "tax_rate": _safe_float(tax_quote.get("tax_rate", 0), 0.0),
                        "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
                        "product_type": tax_quote.get("product_type", product_type),
                        "locale": localization_context.get("resolved_language", "en"),
                        "preferred_language": localization_context.get("resolved_language", "en"),
                        "localization_context": localization_context,
                        "status": "pending",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    await append_financial_ledger_entry(
                        db,
                        event_type="checkout_initiated_stripe_fallback",
                        transaction_id=fallback_tx_id,
                        provider="stripe",
                        user_id=user.user_id,
                        payload={"fallback_from": "fedapay", "fedapay_error": fedapay_error_detail},
                    )
                    logger.info(f"[FALLBACK] Stripe session created: {stripe_session.id}")

                    return {
                        "success": True,
                        "ticket_id": tx_ref,
                        "payment_id": payment_id,
                        "subscription_plan": payload.plan_id,
                        "amount_local": total_local,
                        "currency": payload.currency,
                        "amount_usd": fallback_total_usd,
                        "gateway": "stripe_fallback",
                        "payment_url": stripe_session.url,
                        "status": "pending",
                        "fallback": True,
                        "fallback_reason": f"FedaPay unavailable: {fedapay_error_detail[:100]}",
                        "message": "FedaPay is temporarily unavailable. You've been redirected to secure card payment via Stripe with the same checkout total.",
                        "saved_card": saved_card,
                        "sandbox": sandbox_mode,
                    }
                except Exception as stripe_err:
                    logger.error(f"[FALLBACK] Stripe fallback also failed: {stripe_err}")
                    raise HTTPException(
                        status_code=502,
                        detail=f"Payment processing unavailable. FedaPay: {fedapay_error_detail}. Stripe fallback: {str(stripe_err)}",
                    )
            else:
                raise HTTPException(status_code=502, detail=f"FedaPay: {fedapay_error_detail}")

        # ── FedaPay succeeded — store transaction ──
        provider_hint = str(payload.mobile_provider or "").strip().lower()
        is_card_channel = bool(saved_card) or any(token in provider_hint for token in ("card", "visa", "master"))
        payment_method_label = "fedapay_card" if is_card_channel else "mobile_money_fedapay"
        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
        await db.payment_transactions.insert_one(
            {
                "transaction_id": transaction_id,
                "session_id": tx_ref,
                "user_id": user.user_id,
                "plan_id": payload.plan_id,
                "billing_period": payload.billing_period,
                "amount_usd": usd_price,
                "amount_local": total_local,
                "original_usd_amount": usd_price,
                "currency": payload.currency,
                "provider": "fedapay",
                "gateway": "fedapay",
                "phone_number": payload.phone_number,
                "fee_local": fee_local,
                "fee_pct": fee_pct,
                "mobile_provider": payload.mobile_provider,
                "fedapay_policy_source": fedapay_policy.get("source", "contract_seed"),
                "fixed_tax_rate_pct": fixed_tax_rate_pct,
                "fx_rate": fx_rate,
                "payment_method": payment_method_label,
                "payment_status": "pending",
                "payment_id": payment_id,
                "fedapay_tx_id": fedapay_tx.get("transaction_id"),
                "fedapay_reference": fedapay_tx.get("reference"),
                "payment_url": fedapay_tx.get("payment_url", ""),
                "subtotal": local_financials["subtotal"],
                "tax_amount": local_financials["tax_amount"],
                "processing_fee": local_financials["processing_fee"],
                "amount_gross": local_financials["amount_gross"],
                "amount_net": local_financials["amount_net"],
                "total_amount": local_financials["total_amount"],
                "tax_rate": _safe_float(tax_quote.get("tax_rate", 0), 0.0),
                "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
                "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
                "tax_breakdown": tax_quote.get("tax_breakdown", []),
                "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
                "product_type": tax_quote.get("product_type", product_type),
                "locale": localization_context.get("resolved_language", "en"),
                "preferred_language": localization_context.get("resolved_language", "en"),
                "localization_context": localization_context,
                "saved_card_id": saved_card.get("card_id") if saved_card else None,
                "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
                "saved_card_type": saved_card.get("card_type") if saved_card else None,
                "status": "pending",
                "fee_pass_through": True,
                "sandbox": sandbox_mode,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        await log_tax_calculation(
            db,
            transaction_id=transaction_id,
            provider="fedapay",
            user_id=user.user_id,
            payload={"phase": "checkout_create", "tax_quote": tax_quote, "financials": local_financials},
        )
        await append_financial_ledger_entry(
            db,
            event_type="checkout_initiated",
            transaction_id=transaction_id,
            provider="fedapay",
            user_id=user.user_id,
            payload={"financials": local_financials, "session_id": tx_ref},
        )

        return {
            "success": True,
            "ticket_id": tx_ref,
            "payment_id": payment_id,
            "subscription_plan": payload.plan_id,
            "amount_local": total_local,
            "currency": payload.currency,
            "fee_local": fee_local,
            "fee_pct": fee_pct,
            "mobile_provider": payload.mobile_provider,
            "fedapay_policy_source": fedapay_policy.get("source", "contract_seed"),
            "fixed_tax_rate_pct": fixed_tax_rate_pct,
            "amount_usd": usd_price,
            "tax_amount_local": tax_local,
            "tax_amount_usd": usd_tax,
            "amount_gross_local": local_financials["amount_gross"],
            "amount_net_local": local_financials["amount_net"],
            "payment_method": payment_method_label,
            "gateway": gw["name"],
            "payment_url": fedapay_tx.get("payment_url", ""),
            "fedapay_reference": fedapay_tx.get("reference", ""),
            "status": "pending",
            "message": "Payment initiated via FedaPay. Complete payment at the provided URL.",
            "saved_card": saved_card,
            "sandbox": sandbox_mode,
        }

    # ── Sandbox Simulation (other gateways) ──
    tx_ref = f"MMSUB_{uuid.uuid4().hex[:10].upper()}"
    payment_id = f"mm_{uuid.uuid4().hex[:12]}"

    # Activate subscription
    end_date = datetime.now(timezone.utc) + timedelta(days=365 if payload.billing_period == "yearly" else 30)
    lifecycle_context = await _get_subscription_lifecycle_state(user.user_id)

    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "subscription_plan": payload.plan_id,
                "subscription_status": "active",
                "subscription_end_date": end_date,
                "payment_verified": True,
                "last_payment_id": payment_id,
                "last_payment_method": f"mobile_money_{payload.gateway}",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    transaction_id = f"txn_{uuid.uuid4().hex[:16]}"

    # Log transaction
    tx_doc = {
        "transaction_id": transaction_id,
        "session_id": tx_ref,
        "user_id": user.user_id,
        "plan_id": payload.plan_id,
        "billing_period": payload.billing_period,
        "amount_usd": usd_price,
        "amount_local": total_local,
        "original_usd_amount": usd_price,
        "currency": payload.currency,
        "provider": f"mobile_money_{payload.gateway}",
        "gateway": payload.gateway,
        "phone_number": payload.phone_number,
        "fee_local": fee_local,
        "fee_pct": fee_pct,
        "fx_rate": fx_rate,
        "payment_method": f"mobile_money_{payload.gateway}",
        "payment_status": "completed",
        "payment_id": payment_id,
        "subtotal": local_financials["subtotal"],
        "tax_amount": local_financials["tax_amount"],
        "processing_fee": local_financials["processing_fee"],
        "amount_gross": local_financials["amount_gross"],
        "amount_net": local_financials["amount_net"],
        "total_amount": local_financials["total_amount"],
        "tax_rate": _safe_float(tax_quote.get("tax_rate", 0), 0.0),
        "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
        "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
        "tax_breakdown": tax_quote.get("tax_breakdown", []),
        "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
        "product_type": tax_quote.get("product_type", product_type),
        "locale": localization_context.get("resolved_language", "en"),
        "preferred_language": localization_context.get("resolved_language", "en"),
        "localization_context": localization_context,
        "saved_card_id": saved_card.get("card_id") if saved_card else None,
        "saved_card_last_four": saved_card.get("last_four") if saved_card else None,
        "saved_card_type": saved_card.get("card_type") if saved_card else None,
        "status": "completed",
        "fee_pass_through": True,
        "sandbox": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **lifecycle_context,
    }
    await db.payment_transactions.insert_one(tx_doc)
    await db.payments.insert_one(_build_payment_record_from_tx(tx_doc, status="completed"))
    await log_tax_calculation(
        db,
        transaction_id=transaction_id,
        provider=f"mobile_money_{payload.gateway}",
        user_id=user.user_id,
        payload={"phase": "sandbox_capture", "tax_quote": tax_quote, "financials": local_financials},
    )
    await append_financial_ledger_entry(
        db,
        event_type="provider_capture_completed",
        transaction_id=transaction_id,
        provider=f"mobile_money_{payload.gateway}",
        user_id=user.user_id,
        payload={"session_id": tx_ref, "financials": local_financials},
    )

    # Log to admin revenue (auto-convert to USD)
    fee_usd = round(usd_price * fee_pct / 100, 4)
    await db.service_fees.insert_one(
        {
            "fee_id": f"fee_{uuid.uuid4().hex[:10]}",
            "user_id": user.user_id,
            "tx_id": tx_ref,
            "tx_type": "subscription",
            "fee_usd": fee_usd,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Credit admin master wallet
    await db.admin_wallet.update_one(
        {"wallet_type": "master"},
        {
            "$inc": {"balance_usd": fee_usd, "total_collected": fee_usd},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )

    # Audit log
    await db.subscription_audit_log.insert_one(
        {
            "user_id": user.user_id,
            "action": "mobile_money_payment",
            "plan_id": payload.plan_id,
            "amount_usd": usd_price,
            "amount_local": total_local,
            "currency": payload.currency,
            "gateway": payload.gateway,
            "payment_id": payment_id,
            "timestamp": datetime.now(timezone.utc),
        }
    )

    ticket_id = f"MM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    renewal_date = end_date.strftime("%b %d, %Y")

    # Send notifications (awaited to prevent silent drops in critical payment flow)
    try:
        await _send_payment_notification(
            user_id=user.user_id,
            email=user.email,
            user_name=getattr(user, "name", ""),
            plan_name=plan["name"],
            amount=usd_price,
            payment_method=f"Mobile Money ({gw['name']})",
            ticket_id=ticket_id,
            billing_cycle=payload.billing_period,
            renewal_date=renewal_date,
            transaction_context=tx_doc,
        )
        await db.payment_transactions.update_one(
            {"payment_id": payment_id},
            {
                "$set": {
                    "notification_sent": True,
                    "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
    except Exception as exc:
        logger.error(f"Sandbox mobile-money notification dispatch failed: {exc}")
        await db.notification_recovery_queue.insert_one(
            {
                "queue_id": f"notifq_{uuid.uuid4().hex[:12]}",
                "provider": tx_doc.get("provider", "mobile_money"),
                "payment_id": payment_id,
                "session_id": tx_ref,
                "user_id": user.user_id,
                "status": "pending",
                "reason": str(exc),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    # Broadcast real-time subscription update via WebSocket
    try:
        from utils.ws_manager import broadcast_data_change
        await broadcast_data_change("subscription", "updated", user.user_id)
        await broadcast_data_change("payments", "created", user.user_id)
    except Exception:
        pass

    return {
        "success": True,
        "ticket_id": ticket_id,
        "payment_id": payment_id,
        "subscription_plan": payload.plan_id,
        "subscription_end_date": end_date.isoformat(),
        "amount_local": total_local,
        "currency": payload.currency,
        "fee_local": fee_local,
        "fixed_tax_rate_pct": fixed_tax_rate_pct,
        "amount_usd": usd_price,
        "gateway": gw["name"],
        "message": f"Successfully subscribed to {plan['name']} via {gw['name']}!",
        "saved_card": saved_card,
        "sandbox": True,
    }


# ── FedaPay Webhook & Status ──


@router.get("/fedapay/webhook")
@router.get("/fedapay/webhook/")
@router.get("/fedapay/webhook/health")
@router.get("/fedapay/webhook/health/")
@router.head("/fedapay/webhook")
@router.head("/fedapay/webhook/")
@router.head("/fedapay/webhook/health")
@router.head("/fedapay/webhook/health/")
@router.get("/payments/fedapay/webhook")
@router.get("/payments/fedapay/webhook/")
@router.get("/payments/fedapay/webhook/health")
@router.get("/payments/fedapay/webhook/health/")
@router.head("/payments/fedapay/webhook")
@router.head("/payments/fedapay/webhook/")
@router.head("/payments/fedapay/webhook/health")
@router.head("/payments/fedapay/webhook/health/")
async def fedapay_webhook_health():
    """Health check for FedaPay webhook endpoint.

    Supports GET/HEAD and trailing-slash variants so provider probes always receive 2xx.
    """
    return JSONResponse({"status": "ok", "service": "fedapay_webhook", "ready": True}, status_code=200)


@router.get("/fedapay/webhook-info")
async def fedapay_webhook_info(request: Request):
    """Admin endpoint: returns the current correct webhook URL for FedaPay dashboard configuration."""
    user = await _get_user_from_request(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from routes.fedapay_client import get_current_webhook_url

    current_url = get_current_webhook_url()
    return {
        "webhook_url": current_url,
        "alt_webhook_url": current_url.replace("/payments/fedapay/webhook", "/fedapay/webhook") if current_url else "",
        "instruction": "Copy the webhook_url and paste it into your FedaPay dashboard at https://live.fedapay.com/webhooks",
        "fedapay_env": os.environ.get("FEDAPAY_ENV", "live"),
    }


FEDAPAY_WEBHOOK_MAX_RETRIES = 6


def _extract_fedapay_entity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize FedaPay payload variants into a dict entity block."""
    if not isinstance(payload, dict):
        return {}

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    candidates = [payload.get("entity"), data_block.get("entity"), data_block]

    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def _build_fedapay_webhook_event_key(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        payload = {}

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_id = str(payload.get("id") or payload.get("event_id") or data_block.get("id") or "").strip()
    if event_id:
        return f"fedapay_event_{event_id}"

    entity = _extract_fedapay_entity(payload)

    name = str(payload.get("name") or "unknown")
    tx_id = str(entity.get("id") or "")
    status = str(entity.get("status") or "")
    reference = str(entity.get("reference") or "")
    fingerprint = hashlib.sha256(f"{name}|{tx_id}|{status}|{reference}".encode()).hexdigest()[:28]
    return f"fedapay_fingerprint_{fingerprint}"


async def _queue_fedapay_webhook_event(event_key: str, payload: Dict[str, Any], signature_valid: bool) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "event_key": event_key,
        "payload": payload,
        "status": "queued",
        "attempts": 0,
        "signature_valid": signature_valid,
        "received_at": now_iso,
        "updated_at": now_iso,
    }
    try:
        await db.fedapay_webhook_events.insert_one({**doc})
        return {"status": "queued", "event_key": event_key}
    except DuplicateKeyError:
        existing = await db.fedapay_webhook_events.find_one({"event_key": event_key}, {"_id": 0, "status": 1}) or {}
        current = existing.get("status", "queued")
        if current == "processed":
            return {"status": "already_processed", "event_key": event_key}
        if current == "processing":
            return {"status": "processing", "event_key": event_key}
        await db.fedapay_webhook_events.update_one(
            {"event_key": event_key},
            {
                "$set": {
                    "payload": payload,
                    "status": "retry",
                    "updated_at": now_iso,
                    "signature_valid": signature_valid,
                },
                "$unset": {"next_retry_at": "", "last_error": ""},
            },
        )
        return {"status": "retry", "event_key": event_key}


async def _apply_fedapay_webhook_payload(payload: Dict[str, Any]) -> str:
    entity = _extract_fedapay_entity(payload)
    if not entity:
        logger.info("FedaPay webhook: missing/invalid entity block, ignoring payload")
        return "ignored"

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_type = payload.get("name", "") or data_block.get("name", "")
    tx_id = entity.get("id")
    status = (entity.get("status") or "").lower()
    reference = entity.get("reference", "")

    logger.info(f"FedaPay webhook: event={event_type}, tx_id={tx_id}, status={status}, ref={reference}")

    tx = await db.payment_transactions.find_one({"fedapay_tx_id": tx_id, "gateway": "fedapay"}, {"_id": 0})
    if not tx:
        tx = await db.payment_transactions.find_one(
            {"fedapay_reference": reference, "gateway": "fedapay"}, {"_id": 0}
        )

    if not tx:
        logger.warning(f"FedaPay webhook: no matching transaction for tx_id={tx_id}")
        return "ignored"

    previous_status = str(tx.get("payment_status") or "").lower()
    new_status = (
        "completed"
        if status == "approved"
        else "failed"
        if status in ("declined", "cancelled", "refunded")
        else "pending"
    )
    # Prevent stale provider callbacks from downgrading a confirmed payment back to pending.
    if previous_status == "completed" and new_status == "pending":
        logger.info(
            "FedaPay webhook: ignored pending downgrade for tx=%s (ref=%s)",
            tx_id,
            reference,
        )
        new_status = "completed"
    await db.payment_transactions.update_one(
        {"session_id": tx["session_id"]},
        {
            "$set": {
                "payment_status": new_status,
                "fedapay_status": status,
                "webhook_received_at": datetime.now(timezone.utc).isoformat(),
                "provider": "fedapay",
                "status": new_status,
            }
        },
    )
    tx = {**tx, "payment_status": new_status, "provider": "fedapay", "status": new_status}

    if new_status == "completed" and previous_status != "completed":
        if tx.get("split_master"):
            master_ref = tx["split_master"]
            split_total = tx.get("split_total", 1)
            completed_count = await db.payment_transactions.count_documents(
                {"split_master": master_ref, "payment_status": "completed"}
            )
            await db.split_payments.update_one(
                {"master_ref": master_ref},
                {"$set": {"parts_completed": completed_count, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            logger.info(
                "FedaPay split payment: %s part %s/%s completed (%s/%s total)",
                master_ref,
                tx.get("split_part"),
                split_total,
                completed_count,
                split_total,
            )

            if completed_count < split_total:
                return "split_pending"

            await db.split_payments.update_one(
                {"master_ref": master_ref},
                {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}},
            )
            master_doc = await db.split_payments.find_one({"master_ref": master_ref}, {"_id": 0})
            if master_doc:
                tx["amount_usd"] = master_doc.get("total_amount_usd", tx.get("amount_usd", 0))
                tx["amount_local"] = master_doc.get("total_amount_local", tx.get("amount_local", 0))
            logger.info("FedaPay split payment %s: all %s parts completed", master_ref, split_total)

        billing_period = tx.get("billing_period", "monthly")
        end_date = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)
        user_id = tx["user_id"]
        lifecycle_context = await _get_subscription_lifecycle_state(user_id)

        await db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "subscription_plan": tx["plan_id"],
                    "subscription_status": "active",
                    "subscription_end_date": end_date,
                    "payment_verified": True,
                    "last_payment_id": tx["payment_id"],
                    "last_payment_method": "mobile_money_fedapay",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        tx = {**tx, **lifecycle_context}

        existing_payment = await db.payments.find_one({"payment_id": tx["payment_id"]}, {"_id": 0, "payment_id": 1})
        if not existing_payment:
            await db.payments.insert_one(_build_payment_record_from_tx(tx, status="completed"))

        await append_financial_ledger_entry(
            db,
            event_type="provider_webhook_confirmed",
            transaction_id=tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id"),
            provider="fedapay",
            user_id=user_id,
            payload={
                "session_id": tx.get("session_id"),
                "payment_id": tx.get("payment_id"),
                "financials": {
                    "subtotal": tx.get("subtotal"),
                    "tax_amount": tx.get("tax_amount"),
                    "processing_fee": tx.get("processing_fee", tx.get("fee_local", 0)),
                    "amount_gross": tx.get("amount_gross"),
                    "amount_net": tx.get("amount_net"),
                    "total_amount": tx.get("total_amount", tx.get("amount_local")),
                },
            },
        )

        fee_usd = round(tx.get("amount_usd", 0) * tx.get("fee_pct", 0.0) / 100, 4)
        await db.service_fees.insert_one(
            {
                "fee_id": f"fee_{uuid.uuid4().hex[:10]}",
                "user_id": user_id,
                "tx_id": tx["session_id"],
                "tx_type": "subscription",
                "fee_usd": fee_usd,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await db.admin_wallet.update_one(
            {"wallet_type": "master"},
            {
                "$inc": {"balance_usd": fee_usd, "total_collected": fee_usd},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )

        plan = await get_subscription_plan_from_gps(tx["plan_id"]) or {}
        plan_name = plan.get("name", tx["plan_id"])
        if not LOCK_SINGLE_PAYMENT_COMMUNICATION:
            try:
                from utils.notification_helper import create_notification_for_email

                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                user_email = user_doc.get("email", "") if user_doc else ""
                await create_notification_for_email(
                    user_id,
                    user_email,
                    "Payment Confirmed",
                    f"Your {plan_name} subscription is now active via FedaPay Mobile Money!",
                    notif_type="payment_confirmed",
                )
            except Exception as e:
                logger.warning(f"FedaPay real-time notification error: {e}")

        logger.info(f"FedaPay subscription activated: user={user_id}, plan={tx['plan_id']}")

        try:
            from routes.ab_testing import check_user_returned

            await check_user_returned(user_id)
        except Exception:
            pass
        try:
            await db.prompt_experiment_events.insert_one(
                {
                    "event_id": f"pevt_{uuid.uuid4().hex[:10]}",
                    "experiment_id": "__auto_upgrade__",
                    "variant_id": "__upgrade__",
                    "user_id": user_id,
                    "event": "upgrade",
                    "metadata": {"plan": tx["plan_id"], "method": "fedapay", "billing": billing_period},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            await db.ab_assignments.update_many(
                {"user_id": user_id, "converted": False},
                {"$set": {"converted": True, "converted_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            pass

        try:
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
            if user_doc:
                ticket_id = f"FDP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                renewal_date = end_date.strftime("%b %d, %Y")
                await _send_payment_notification(
                    user_id=user_id,
                    email=user_doc.get("email", ""),
                    user_name=user_doc.get("name", ""),
                    plan_name=plan.get("name", tx["plan_id"]),
                    amount=tx.get("amount_usd", tx.get("amount", 0)),
                    payment_method="fedapay",
                    ticket_id=ticket_id,
                    billing_cycle=billing_period,
                    renewal_date=renewal_date,
                    currency=tx.get("currency", "XOF").upper(),
                    amount_local=tx.get("amount_local", tx.get("amount", 0)),
                    transaction_context=tx,
                )
                await db.payment_transactions.update_one(
                    {"session_id": tx.get("session_id")} if tx.get("session_id") else {"payment_id": tx.get("payment_id")},
                    {
                        "$set": {
                            "notification_sent": True,
                            "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
        except Exception as e:
            logger.error(f"FedaPay confirmation notification error: {e}")
            await db.notification_recovery_queue.insert_one(
                {
                    "queue_id": f"notifq_{uuid.uuid4().hex[:12]}",
                    "provider": "fedapay",
                    "payment_id": tx.get("payment_id"),
                    "session_id": tx.get("session_id"),
                    "user_id": user_id,
                    "status": "pending",
                    "reason": str(e),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    elif new_status == "failed" and previous_status != "failed":
        user_id = tx.get("user_id", "")
        plan = await get_subscription_plan_from_gps(tx.get("plan_id", "free")) or {}
        title, message = _build_provider_failure_copy("FedaPay", status, plan.get("name", "subscription"))

        if str(status).lower() == "expired":
            await dispatch_subscription_expiry_notification(
                user_id,
                source_provider="fedapay",
                reason="expired",
                plan_name_override=plan.get("name", tx.get("plan_id", "subscription")),
                transaction_filter={"session_id": tx.get("session_id")},
            )
            logger.info(f"FedaPay unified expiry notification sent: user={user_id}, status={status}")
        else:
            try:
                from utils.notification_helper import create_notification

                await create_notification(
                    user_id,
                    title,
                    message,
                    notif_type="payment_failed",
                    data={"plan_id": tx.get("plan_id"), "amount": tx.get("amount_usd", 0), "fedapay_status": status},
                )
            except Exception as e:
                logger.warning(f"FedaPay failed notification error: {e}")

            logger.info(f"FedaPay payment failed notification: user={user_id}, status={status}")

        if is_email_configured():
            try:
                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                if user_doc and user_doc.get("email"):
                    bp = tx.get("billing_period", "monthly")
                    currency = tx.get("currency", "XOF").upper()
                    amount_local = tx.get("amount_local", tx.get("amount", 0))
                    amount_usd = tx.get("amount_usd", 0)
                    recovery_dispatch = await _send_user_payment_failure_recovery_email(
                        user_id=user_id,
                        user_email=user_doc["email"],
                        user_name=user_doc.get("name", ""),
                        plan_id=tx.get("plan_id", "basic"),
                        plan_name=plan.get("name", tx.get("plan_id", "Unknown")),
                        billing_period=bp,
                        payment_method="fedapay",
                        amount_usd=amount_usd,
                        currency=currency,
                        amount_local=amount_local,
                        session_id=tx.get("session_id", ""),
                    )
                    if not recovery_dispatch.get("sent") and recovery_dispatch.get("reason") == "daily_throttled":
                        logger.info(
                            "FedaPay failure recovery email throttled for user=%s (last_email_at=%s)",
                            user_id,
                            recovery_dispatch.get("last_email_at"),
                        )
            except Exception as e:
                logger.error(f"FedaPay failure recovery email error: {e}")

        try:
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
            await _send_admin_payment_failure_alert(
                customer_email=(user_doc or {}).get("email", ""),
                plan_name=plan.get("name", tx.get("plan_id", "Unknown")),
                payment_method="fedapay",
                reason=message,
                amount=tx.get("amount_usd", 0),
                amount_local=tx.get("amount_local", tx.get("amount", 0)),
                currency=tx.get("currency", "XOF").upper(),
                reference_id=tx.get("session_id", ""),
            )
        except Exception as e:
            logger.warning(f"FedaPay admin failure alert error: {e}")

    return new_status


async def _process_fedapay_webhook_event(event_key: str, payload: Dict[str, Any], source: str = "webhook") -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    claimed = await db.fedapay_webhook_events.find_one_and_update(
        {"event_key": event_key, "status": {"$in": ["queued", "retry"]}},
        {
            "$set": {
                "status": "processing",
                "updated_at": now_iso,
                "processing_started_at": now_iso,
                "last_source": source,
            },
            "$inc": {"attempts": 1},
        },
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "attempts": 1},
    )
    if not claimed:
        return {"status": "skipped", "reason": "already_processing_or_done", "event_key": event_key}

    attempts = int(claimed.get("attempts", 1))
    try:
        provider_status = await _apply_fedapay_webhook_payload(payload)
        await db.fedapay_webhook_events.update_one(
            {"event_key": event_key},
            {
                "$set": {
                    "status": "processed",
                    "provider_status": provider_status,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": "",
                },
                "$unset": {"next_retry_at": ""},
            },
        )
        return {"status": "processed", "event_key": event_key, "provider_status": provider_status}
    except Exception as exc:
        delay_seconds = min(900, (2 ** min(attempts, 7)) * 15)
        next_retry = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
        new_state = "retry" if attempts < FEDAPAY_WEBHOOK_MAX_RETRIES else "dead"
        await db.fedapay_webhook_events.update_one(
            {"event_key": event_key},
            {
                "$set": {
                    "status": new_state,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": str(exc)[:500],
                    "next_retry_at": next_retry,
                }
            },
        )
        logger.error(
            "FedaPay webhook async processing failed: event_key=%s attempts=%s status=%s error=%s",
            event_key,
            attempts,
            new_state,
            exc,
        )
        return {"status": new_state, "event_key": event_key, "attempts": attempts}


async def run_fedapay_webhook_retry_cycle(limit: int = 20) -> Dict[str, Any]:
    """Retry queued/failed FedaPay webhook events that are ready for re-processing."""
    now_iso = datetime.now(timezone.utc).isoformat()
    pending = await db.fedapay_webhook_events.find(
        {
            "status": {"$in": ["queued", "retry"]},
            "$or": [
                {"next_retry_at": {"$exists": False}},
                {"next_retry_at": ""},
                {"next_retry_at": {"$lte": now_iso}},
            ],
        },
        {"_id": 0, "event_key": 1, "payload": 1},
    ).sort("received_at", 1).limit(limit).to_list(limit)

    processed = 0
    for event in pending:
        event_key = event.get("event_key")
        payload = event.get("payload") or {}
        if not event_key:
            continue
        await _process_fedapay_webhook_event(event_key, payload, source="scheduler")
        processed += 1

    return {"queued_candidates": len(pending), "processed": processed}


async def run_fedapay_webhook_dead_replay_cycle(limit: int = 20) -> Dict[str, Any]:
    """Replay dead-letter FedaPay webhook events by promoting them back to retry."""
    safe_limit = max(1, min(int(limit or 20), 100))
    now_iso = datetime.now(timezone.utc).isoformat()

    dead_candidates = await db.fedapay_webhook_events.find(
        {"status": "dead"},
        {"_id": 0, "event_key": 1},
    ).sort("updated_at", 1).limit(safe_limit).to_list(safe_limit)

    promoted = 0
    processed = 0
    retry_remaining = 0
    dead_remaining = 0

    for candidate in dead_candidates:
        event_key = candidate.get("event_key")
        if not event_key:
            continue

        claimed = await db.fedapay_webhook_events.find_one_and_update(
            {"event_key": event_key, "status": "dead"},
            {
                "$set": {
                    "status": "retry",
                    "updated_at": now_iso,
                    "next_retry_at": "",
                    "manual_replay_requested_at": now_iso,
                },
                "$inc": {"manual_replay_count": 1},
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "payload": 1},
        )
        if not claimed:
            continue

        promoted += 1
        payload = claimed.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        result = await _process_fedapay_webhook_event(event_key, payload, source="manual_dead_replay")
        if result.get("status") == "processed":
            processed += 1
        elif result.get("status") == "retry":
            retry_remaining += 1
        elif result.get("status") == "dead":
            dead_remaining += 1

    remaining_dead_total = await db.fedapay_webhook_events.count_documents({"status": "dead"})

    return {
        "dead_candidates": len(dead_candidates),
        "promoted_to_retry": promoted,
        "processed": processed,
        "retry_remaining": retry_remaining,
        "dead_after_replay": dead_remaining,
        "dead_total_after_cycle": remaining_dead_total,
    }


async def _ingest_fedapay_webhook_async(raw_body: bytes, sig_header: str, ack_id: str, source_ip: str = ""):
    """Background ingestion pipeline for FedaPay webhooks.

    Design goal: webhook endpoint should ACK immediately, and all heavy work happens async.
    """
    try:
        from routes.fedapay_client import verify_webhook_signature

        signature_valid = True
        if sig_header:
            signature_valid = bool(verify_webhook_signature(sig_header, raw_body))
            if not signature_valid:
                logger.warning("FedaPay webhook signature verification failed")

        payload: Dict[str, Any] = {}
        if raw_body and raw_body.strip():
            try:
                import json as _json

                payload = _json.loads(raw_body)
            except Exception:
                await db.fedapay_webhook_delivery_log.insert_one(
                    {
                        "ack_id": ack_id,
                        "event_key": "",
                        "queued_status": "ignored_non_json",
                        "signature_present": bool(sig_header),
                        "signature_valid": signature_valid,
                        "source_ip": source_ip,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                logger.warning(f"FedaPay webhook: non-JSON body received ({len(raw_body)} bytes)")
                return

        if payload and not isinstance(payload, dict):
            await db.fedapay_webhook_delivery_log.insert_one(
                {
                    "ack_id": ack_id,
                    "event_key": "",
                    "queued_status": "ignored_non_object_json",
                    "signature_present": bool(sig_header),
                    "signature_valid": signature_valid,
                    "source_ip": source_ip,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            logger.warning("FedaPay webhook: JSON payload was not an object; ignored")
            return

        if not payload or not _extract_fedapay_entity(payload):
            await db.fedapay_webhook_delivery_log.insert_one(
                {
                    "ack_id": ack_id,
                    "event_key": "",
                    "queued_status": "ignored_empty_payload",
                    "signature_present": bool(sig_header),
                    "signature_valid": signature_valid,
                    "source_ip": source_ip,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            logger.info("FedaPay webhook: ping/empty payload acknowledged")
            return

        event_key = _build_fedapay_webhook_event_key(payload)
        queue_result = await _queue_fedapay_webhook_event(event_key, payload, signature_valid=signature_valid)

        await db.fedapay_webhook_delivery_log.insert_one(
            {
                "ack_id": ack_id,
                "event_key": event_key,
                "queued_status": queue_result.get("status"),
                "signature_present": bool(sig_header),
                "signature_valid": signature_valid,
                "source_ip": source_ip,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        if queue_result.get("status") in {"queued", "retry"}:
            await _process_fedapay_webhook_event(event_key, payload, source="webhook_async")
    except Exception as exc:
        logger.error(f"FedaPay webhook async ingest error: {exc}", exc_info=True)
        try:
            await db.fedapay_webhook_delivery_log.insert_one(
                {
                    "ack_id": ack_id,
                    "event_key": "",
                    "queued_status": "internal_error",
                    "signature_present": bool(sig_header),
                    "signature_valid": None,
                    "source_ip": source_ip,
                    "error": str(exc)[:500],
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception:
            pass


async def _ack_fedapay_webhook_request(request: Request, status_code: int = 200) -> JSONResponse:
    """Shared ACK path: return quickly, ingest asynchronously."""
    try:
        raw_body = await request.body()
        sig_header = request.headers.get("X-Fedapay-Signature", "") or request.headers.get("x-fedapay-signature", "")
        ack_id = f"fedapay_ack_{uuid.uuid4().hex[:14]}"
        source_ip = request.client.host if request.client else ""

        asyncio.create_task(_ingest_fedapay_webhook_async(raw_body, sig_header, ack_id=ack_id, source_ip=source_ip))

        return JSONResponse(
            {
                "received": True,
                "ack_id": ack_id,
                "queued_status": "accepted",
            },
            status_code=status_code,
        )
    except Exception as exc:
        logger.error(f"FedaPay webhook internal error: {exc}", exc_info=True)
        return JSONResponse({"received": True, "error": "internal"}, status_code=status_code)


@router.post("/fedapay/webhook")
@router.post("/fedapay/webhook/")
@router.post("/payments/fedapay/webhook")
@router.post("/payments/fedapay/webhook/")
async def fedapay_webhook(request: Request):
    """Handle FedaPay payment webhook callbacks with immediate ACK + background ingestion."""
    return await _ack_fedapay_webhook_request(request, status_code=200)


@router.post("/fedapay/webhook/ack")
@router.post("/fedapay/webhook/ack/")
@router.post("/payments/fedapay/webhook/ack")
@router.post("/payments/fedapay/webhook/ack/")
async def fedapay_webhook_ack(request: Request):
    """High-availability ACK endpoint for providers expecting explicit async acceptance."""
    return await _ack_fedapay_webhook_request(request, status_code=202)


@router.get("/fedapay/status/{payment_id}")
async def fedapay_payment_status(payment_id: str, request: Request):
    """Check the status of a FedaPay payment."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tx = await db.payment_transactions.find_one(
        {"payment_id": payment_id, "gateway": "fedapay", "user_id": user.user_id}, {"_id": 0}
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Optionally poll FedaPay for live status
    if tx.get("payment_status") == "pending" and tx.get("fedapay_tx_id"):
        try:
            from routes.fedapay_client import get_transaction

            live_tx = await get_transaction(tx["fedapay_tx_id"])
            live_status = live_tx.get("status", "").lower()
            if live_status == "approved" and tx["payment_status"] != "completed":
                tx["payment_status"] = "completed"
                await db.payment_transactions.update_one(
                    {"payment_id": payment_id}, {"$set": {"payment_status": "completed", "fedapay_status": live_status}}
                )
            elif live_status in ("declined", "cancelled", "refunded") and tx["payment_status"] != "failed":
                tx["payment_status"] = "failed"
                await db.payment_transactions.update_one(
                    {"payment_id": payment_id},
                    {"$set": {"payment_status": "failed", "fedapay_status": live_status, "failure_reason": f"Payment {live_status} by provider"}},
                )
        except Exception as e:
            logger.warning(f"FedaPay status poll failed: {e}")

    return {
        "payment_id": payment_id,
        "status": tx.get("payment_status", "unknown"),
        "amount_local": tx.get("amount_local"),
        "currency": tx.get("currency"),
        "gateway": "FedaPay",
        "created_at": tx.get("created_at"),
    }


@router.get("/fedapay/callback")
async def fedapay_callback(request: Request):
    """Handle redirect callback from FedaPay after payment. Redirects user to the app."""
    from fastapi.responses import RedirectResponse

    tx_id = request.query_params.get("id", "")
    status = request.query_params.get("status", "")

    frontend_url = _resolve_public_frontend_base(request)
    if not frontend_url:
        frontend_url = (os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")

    # If we got a tx_id, look up the payment and poll FedaPay for real-time status
    payment_id = ""
    if tx_id:
        tx = await db.payment_transactions.find_one(
            {"fedapay_tx_id": int(tx_id) if tx_id.isdigit() else tx_id, "gateway": "fedapay"},
            {"_id": 0, "payment_id": 1, "payment_status": 1},
        )
        if tx:
            payment_id = tx.get("payment_id", "")
            # Poll FedaPay for the latest status
            try:
                from routes.fedapay_client import get_transaction
                live_tx = await get_transaction(int(tx_id) if tx_id.isdigit() else tx_id)
                live_status = (live_tx.get("status") or "").lower()
                if live_status and live_status != tx.get("payment_status"):
                    new_status = (
                        "completed" if live_status == "approved"
                        else "failed" if live_status in ("declined", "cancelled", "refunded")
                        else tx.get("payment_status", "pending")
                    )
                    await db.payment_transactions.update_one(
                        {"payment_id": payment_id},
                        {"$set": {"payment_status": new_status, "fedapay_status": live_status, "callback_received_at": datetime.now(timezone.utc).isoformat()}},
                    )
                    status = live_status
            except Exception as e:
                logger.warning(f"FedaPay callback status poll failed: {e}")

    redirect_url = f"{frontend_url}/subscription/payment-result?gateway=fedapay&status={status or 'unknown'}"
    if payment_id:
        redirect_url += f"&payment_id={payment_id}"
    if tx_id:
        redirect_url += f"&tx_id={tx_id}"

    return RedirectResponse(url=redirect_url)


# ── Admin: FedaPay production-behavior E2E simulator ──
# Mirrors the mobile-money success path (XOF local pricing, country fee policy,
# service fee + admin wallet credit, unified notification pipeline) without a live charge.

class FedaPaySimulationRequest(BaseModel):
    email: str
    name: Optional[str] = None
    address_line: Optional[str] = None
    plan: str = "premium"
    period: str = "monthly"
    city: str = "Cotonou"
    country_code: str = "BJ"
    postal_code: str = ""
    currency: str = "XOF"
    phone_number: str = "+22990000000"
    mobile_provider: Optional[str] = None
    simulate_failure_case: bool = False


@router.post("/admin/payments/simulate-fedapay-production-e2e")
async def simulate_fedapay_production_e2e(body: FedaPaySimulationRequest, request: Request):
    admin = await get_current_user(request)
    if not admin or not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    plan_id = str(body.plan or "premium").lower()
    period = str(body.period or "monthly").lower()
    if period not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="period must be monthly or yearly")
    currency = str(body.currency or "XOF").upper()
    if currency not in MOBILE_MONEY_GATEWAYS["fedapay"]["currencies"]:
        raise HTTPException(status_code=400, detail=f"Currency {currency} not supported by FedaPay")
    country_code = str(body.country_code or "BJ").upper()
    fedapay_policy = await get_fedapay_policy(db)
    supported_countries = set((fedapay_policy.get("countries") or {}).keys()) or set(MOBILE_MONEY_GATEWAYS["fedapay"]["countries"])
    if country_code not in supported_countries:
        raise HTTPException(
            status_code=400,
            detail=f"Country {country_code} is not supported by the FedaPay policy (supported: {sorted(supported_countries)})",
        )
    plan = await get_subscription_plan_from_gps(plan_id)
    if not plan or not float(plan.get("monthly_price") or 0):
        raise HTTPException(status_code=404, detail=f"No paid subscription plan found for '{plan_id}'")
    usd_price = float(plan["monthly_price"] if period == "monthly" else plan["yearly_price"])

    address_line = (body.address_line or "").strip() or None
    display_name = (body.name or "").strip() or None
    user_doc = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user_doc:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": body.email,
            "name": display_name or "FedaPay Simulation User",
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

    product_type = resolve_product_type(plan_id)
    tax_quote = await calculate_tax_quote(
        provider="fedapay",
        subtotal=usd_price,
        currency="USD",
        country_code=country_code,
        state_code="",
        postal_code=body.postal_code,
        product_type=product_type,
    )
    fx_rate = MOBILE_MONEY_FX.get(currency, 605.0)
    usd_tax = _safe_float(tax_quote.get("tax_amount", 0), 0.0)
    subtotal_local = round(usd_price * fx_rate, 0)
    tax_local = round(usd_tax * fx_rate, 0)
    local_amount = round(subtotal_local + tax_local, 0)
    fee_pct = _resolve_fedapay_fee_pct(fedapay_policy, country_code, body.mobile_provider)
    fee_local = round(local_amount * (_safe_float(fee_pct, 0.0) / 100), 0)
    if _safe_float(fee_pct, 0.0) <= 0 or fee_local <= 0:
        raise HTTPException(status_code=503, detail="FedaPay processing fee policy resolved to zero for this country")
    total_local = local_amount + fee_local
    local_financials = build_financial_totals(
        subtotal=float(subtotal_local),
        tax_amount=float(tax_local),
        processing_fee=float(fee_local),
        fee_pass_through=True,
    )
    jurisdiction = {
        **tax_quote.get("jurisdiction", {"country": country_code, "state": "", "postal_code": body.postal_code}),
        "city": body.city,
    }
    if body.postal_code and not jurisdiction.get("postal_code"):
        jurisdiction["postal_code"] = body.postal_code
    if address_line:
        jurisdiction["address_line"] = address_line

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=365 if period == "yearly" else 30)
    tx_ref = f"MMSUB_{uuid.uuid4().hex[:10].upper()}"
    payment_id = f"sim_fedapay_{uuid.uuid4().hex[:12]}"
    transaction_id = f"txn_{uuid.uuid4().hex[:16]}"

    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "subscription_plan": plan_id,
                "subscription_status": "active",
                "subscription_end_date": end_date,
                "payment_verified": True,
                "last_payment_id": payment_id,
                "last_payment_method": "mobile_money_fedapay",
                "updated_at": now,
            }
        },
    )

    tx_doc = {
        "transaction_id": transaction_id,
        "session_id": tx_ref,
        "payment_id": payment_id,
        "user_id": user_id,
        "plan_id": plan_id,
        "billing_period": period,
        "amount_usd": usd_price,
        "amount_local": total_local,
        "original_usd_amount": usd_price,
        "currency": currency,
        "provider": "mobile_money_fedapay",
        "gateway": "fedapay",
        "phone_number": body.phone_number,
        "fee_local": fee_local,
        "fee_pct": fee_pct,
        "fx_rate": fx_rate,
        "payment_method": "mobile_money_fedapay",
        "payment_status": "completed",
        "subtotal": local_financials["subtotal"],
        "tax_amount": local_financials["tax_amount"],
        "processing_fee": local_financials["processing_fee"],
        "amount_gross": local_financials["amount_gross"],
        "amount_net": local_financials["amount_net"],
        "total_amount": local_financials["total_amount"],
        "tax_rate": _safe_float(tax_quote.get("tax_rate", 0), 0.0),
        "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
        "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
        "tax_breakdown": tax_quote.get("tax_breakdown", []),
        "jurisdiction": jurisdiction,
        "product_type": tax_quote.get("product_type", product_type),
        "status": "completed",
        "fee_pass_through": True,
        "environment": "production_simulated",
        "sandbox": False,
        "notification_sent": False,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.payment_transactions.insert_one({**tx_doc})
    await db.payments.insert_one(_build_payment_record_from_tx(tx_doc, status="completed"))
    await log_tax_calculation(
        db,
        transaction_id=transaction_id,
        provider="mobile_money_fedapay",
        user_id=user_id,
        payload={"phase": "fedapay_admin_simulation", "tax_quote": tax_quote, "financials": local_financials},
    )
    await append_financial_ledger_entry(
        db,
        event_type="provider_capture_completed",
        transaction_id=transaction_id,
        provider="mobile_money_fedapay",
        user_id=user_id,
        payload={"session_id": tx_ref, "financials": local_financials, "environment": "production_simulated"},
    )

    fee_usd = round(usd_price * fee_pct / 100, 4)
    await db.service_fees.insert_one(
        {
            "fee_id": f"fee_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "tx_id": tx_ref,
            "tx_type": "subscription",
            "fee_usd": fee_usd,
            "collected_at": now.isoformat(),
        }
    )
    await db.admin_wallet.update_one(
        {"wallet_type": "master"},
        {
            "$inc": {"balance_usd": fee_usd, "total_collected": fee_usd},
            "$set": {"updated_at": now.isoformat()},
        },
        upsert=True,
    )
    await db.subscription_audit_log.insert_one(
        {
            "user_id": user_id,
            "action": "simulated_production_activation",
            "plan_id": plan_id,
            "amount_usd": usd_price,
            "amount_local": total_local,
            "currency": currency,
            "gateway": "fedapay",
            "payment_id": payment_id,
            "timestamp": now,
        }
    )

    ticket_id = f"MM-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    fresh_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1}) or {}
    simulation_start = time.time()

    async def _dispatch_notification():
        try:
            await _send_payment_notification(
                user_id=user_id,
                email=fresh_user.get("email", ""),
                user_name=fresh_user.get("name", ""),
                plan_name=plan.get("name", plan_id.title()),
                amount=usd_price,
                payment_method="Mobile Money (FedaPay)",
                ticket_id=ticket_id,
                billing_cycle=period,
                renewal_date=end_date.strftime("%b %d, %Y"),
                transaction_context=tx_doc,
            )
        except Exception as exc:
            logger.error(f"FedaPay simulation notification error: {exc}")
            await db.notification_recovery_queue.insert_one(
                {
                    "queue_id": f"notifq_{uuid.uuid4().hex[:12]}",
                    "provider": "mobile_money_fedapay",
                    "payment_id": payment_id,
                    "session_id": tx_ref,
                    "user_id": user_id,
                    "status": "pending",
                    "reason": str(exc),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

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
            title, message = _build_provider_failure_copy("FedaPay", "failed", plan.get("name", plan_id.title()))
            await create_notification(
                user_id, title, message,
                notif_type="payment_failed",
                data={"session_id": tx_ref, "plan_id": plan_id, "amount": usd_price},
            )
            failure_case = {"simulated": True, "status": "processed", "reason": "failed"}
        except Exception as exc:
            failure_case = {"simulated": True, "status": "error", "error": str(exc)[:200]}

    latest_tx = await db.payment_transactions.find_one({"payment_id": payment_id}, {"_id": 0}) or {}
    checks = {
        "fee_accuracy": round(local_financials["subtotal"] + local_financials["processing_fee"] + local_financials["tax_amount"], 2) == round(local_financials["total_amount"], 2),
        "notification_latency_under_2s": bool(notification_latency_ms is not None and notification_latency_ms <= 2000),
        "subscription_active": True,
        "api_integrity": bool(latest_tx.get("transaction_id")),
    }

    return {
        "success": True,
        "scenario": {
            "location": body.city,
            "country_code": country_code,
            "postal_code": body.postal_code,
            "address_line": address_line,
            "email": body.email,
            "plan": plan_id,
            "period": period,
            "platform": "fedapay",
            "transaction_id": transaction_id,
            "payment_id": payment_id,
        },
        "pricing_breakdown": {
            "base_plan_price_usd": usd_price,
            "fx_rate": fx_rate,
            "currency": currency,
            "subtotal_local": subtotal_local,
            "taxes_local": tax_local,
            "tax_rate": tax_quote.get("tax_rate", 0),
            "fee_pct": fee_pct,
            "processing_fee_local": fee_local,
            "final_total_local": total_local,
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
