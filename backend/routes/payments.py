"""Payment & Subscription routes: Stripe (card) + PayPal checkout, Resend-backed email confirmations."""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import os
import json
import uuid
import time
import httpx
from urllib.parse import urlparse
from pymongo import ReturnDocument
from emergentintegrations.payments.stripe.checkout import StripeCheckout
from shared.pricing_policy import get_monthly_price_label, get_plan_name
from utils.payment_localization import normalize_language_code
from utils.tax_compliance_engine import (
    append_financial_ledger_entry,
    build_financial_totals,
    log_tax_calculation,
    resolve_product_type,
)
from utils.fedapay_policy_service import (
    resolve_card_fee_pct,
    resolve_mobile_money_fee_pct,
)
from utils.email_service import send_email, is_email_configured, send_catalog_template
from utils.email_templates import (
    build_subscription_confirmation_email,
    build_subscription_restored_email,
)
from utils.payment_recovery import (
    create_recovery_token,
    validate_recovery_token,
    mark_recovered,
    get_recovery_url,
    format_currency,
)
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.pdf_v15_export import enforce_pdf_v15_enterprise as _base_enforce_pdf_v15_enterprise
from utils.pagination import iter_find_paginated
from .db import db, logger, require_admin
from .payments_branding import (
    get_brand_logo_bytes,
    get_brand_logo_public_url,
    get_brand_logo_temp_path,
    get_document_logo_bytes,
    get_document_logo_public_url,
    get_document_logo_temp_path,
)
from .payments_cards import (
    build_saved_card_metadata,
    ensure_default_active_card,
    expire_stale_cards_for_user,
    is_card_expired,
    is_card_expiring_soon,
    mask_card,
    normalize_expiry_year,
    normalize_stored_card_year,
    payment_card_surface,
    resolve_saved_card_for_checkout,
)
from .payments_catalog import get_subscription_plan_from_gps, get_subscription_plans_from_gps, require_paid_subscription_plan
from .payments_export_integrity import (
    build_admin_verifier_prefill_url,
    build_integrity_payload,
    build_integrity_meta,
    format_payment_date_label,
    normalize_export_theme,
    export_theme_palette,
    parse_created_at,
    resolve_plan_name,
    sign_integrity_payload,
)
from .payments_provider_paypal import (
    capture_paypal_order,
    create_paypal_order,
    get_paypal_token,
    verify_paypal_webhook,
)
from .payments_pricing_guard import (
    apply_canonical_plan_pricing,
    assert_plan_pricing_or_block,
    assert_plan_pricing_or_raise_sync,
    normalize_billing_period,
    resolve_plan_pricing_snapshot,
    safe_amount_value,
)
from . import payments_pricing_alerts as _pricing_alerts
from . import payments_cards_routes as _payment_card_routes
from . import payments_subscription_admin as _subscription_admin_routes
from . import payments_reporting_routes as _reporting_routes
from . import payments_recovery_routes as _recovery_routes
from . import payments_paypal_routes as _paypal_routes
from . import payments_fedapay_routes as _fedapay_routes
from . import payments_stripe_routes as _stripe_routes
from . import payment_trust as _payment_trust
from . import payments_history_routes as _history_routes
from . import payments_user_analytics_routes as _user_analytics_routes
from . import payments_admin_maintenance_routes as _admin_maintenance_routes
from . import payments_document_proxy_routes as _document_proxy_routes
from . import payments_checkout_core as _checkout_core
from models.payments import (
    CreateCheckoutRequest,
    ConfirmPaymentRequest,
    CheckoutPreviewRequest,
    PaymentRecord,
)
from .payments_checkout_core import (
    CANONICAL_PAYMENT_METHODS,
    normalize_payment_method,
)
from utils.checkout_kill_switch import (
    DEFAULT_CHECKOUT_PAUSE_MESSAGE,
    get_checkout_kill_switch_state,
    raise_if_checkout_paused,
    set_checkout_kill_switch_state,
)

router = APIRouter()
router.include_router(_pricing_alerts.router)
router.include_router(_subscription_admin_routes.router)
router.include_router(_payment_trust.router)

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")
PAYPAL_API_URL = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID", "")
MOBILE_MONEY_FX = _fedapay_routes.MOBILE_MONEY_FX
MOBILE_MONEY_GATEWAYS = _fedapay_routes.MOBILE_MONEY_GATEWAYS
BRAND_LOGO_URL = os.environ.get("BRAND_LOGO_URL", "")
BRAND_NAME = os.environ.get("BRAND_NAME", "RealAICoach")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")
LOCK_SINGLE_PAYMENT_COMMUNICATION = True

_SHELL_HOSTS = {
    "app.emergent.sh",
    "app.emergentagent.com",
}


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

    scheme = parsed.scheme or "https"
    if scheme not in {"http", "https"}:
        scheme = "https"

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


def _resolve_checkout_frontend_base(req: Request) -> str:
    candidates = [
        _extract_forwarded_host_candidate(req),
        _extract_host_header_candidate(req),
        req.headers.get("origin", ""),
        os.environ.get("REACT_APP_BACKEND_URL", ""),
        os.environ.get("EXPO_PUBLIC_BACKEND_URL", ""),
        FRONTEND_BASE_URL,
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


def _safe_amount_with_fallback(raw: Any, fallback: float = 0.0) -> float:
    value = _safe_amount_value(raw)
    if value == 0.0 and raw not in {0, 0.0, "0", "0.0"}:
        return _safe_amount_value(fallback)
    return value


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    try:
        return _base_enforce_pdf_v15_enterprise(payload, context)
    except Exception:
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")


_get_brand_logo_public_url = get_brand_logo_public_url
_get_document_logo_public_url = get_document_logo_public_url
_get_brand_logo_bytes = get_brand_logo_bytes
_get_document_logo_bytes = get_document_logo_bytes
_get_brand_logo_temp_path = get_brand_logo_temp_path
_get_document_logo_temp_path = get_document_logo_temp_path
_normalize_billing_period = normalize_billing_period
_safe_amount_value = safe_amount_value
_resolve_plan_pricing_snapshot = resolve_plan_pricing_snapshot
_assert_plan_pricing_or_block = assert_plan_pricing_or_block
_assert_plan_pricing_or_raise_sync = assert_plan_pricing_or_raise_sync
_apply_canonical_plan_pricing = apply_canonical_plan_pricing
get_pricing_mismatch_alerts = _pricing_alerts.get_pricing_mismatch_alerts
acknowledge_pricing_mismatch_alert = _pricing_alerts.acknowledge_pricing_mismatch_alert
acknowledge_all_pricing_mismatch_alerts = _pricing_alerts.acknowledge_all_pricing_mismatch_alerts
clear_pricing_mismatch_alerts = _pricing_alerts.clear_pricing_mismatch_alerts
_pricing_mismatch_event_query = _pricing_alerts.pricing_mismatch_event_query
_format_pricing_mismatch_event = _pricing_alerts.format_pricing_mismatch_event
admin_run_subscription_maintenance = _subscription_admin_routes.admin_run_subscription_maintenance
admin_subscription_expiry_overview = _subscription_admin_routes.admin_subscription_expiry_overview
admin_subscription_analytics = _subscription_admin_routes.admin_subscription_analytics
_mask_card = mask_card
_normalize_expiry_year = normalize_expiry_year
_is_card_expired = is_card_expired
_is_card_expiring_soon = is_card_expiring_soon
_payment_card_surface = payment_card_surface
_normalize_stored_card_year = normalize_stored_card_year
_expire_stale_cards_for_user = expire_stale_cards_for_user
_ensure_default_active_card = ensure_default_active_card
_resolve_saved_card_for_checkout = resolve_saved_card_for_checkout
_build_saved_card_metadata = build_saved_card_metadata
_format_payment_date_label = format_payment_date_label
_resolve_plan_name = resolve_plan_name
_parse_created_at = parse_created_at
_normalize_export_theme = normalize_export_theme
_export_theme_palette = export_theme_palette
_build_integrity_meta = build_integrity_meta
_build_integrity_payload = build_integrity_payload
_sign_integrity_payload = sign_integrity_payload
_build_admin_verifier_prefill_url = build_admin_verifier_prefill_url
async def _get_paypal_token():
    return await get_paypal_token(client_id=PAYPAL_CLIENT_ID, secret=PAYPAL_SECRET, api_url=PAYPAL_API_URL)


async def _create_paypal_order(*args, **kwargs):
    return await create_paypal_order(
        client_id=PAYPAL_CLIENT_ID,
        secret=PAYPAL_SECRET,
        api_url=PAYPAL_API_URL,
        safe_amount=_safe_amount_with_fallback,
        zero_decimal_currencies=ZERO_DECIMAL_CURRENCIES,
        logger=logger,
        amount=args[0] if len(args) > 0 else kwargs.pop("amount"),
        plan_name=args[1] if len(args) > 1 else kwargs.pop("plan_name"),
        user_id=args[2] if len(args) > 2 else kwargs.pop("user_id"),
        plan_id=args[3] if len(args) > 3 else kwargs.pop("plan_id"),
        billing_period=args[4] if len(args) > 4 else kwargs.pop("billing_period"),
        return_url=args[5] if len(args) > 5 else kwargs.pop("return_url"),
        cancel_url=args[6] if len(args) > 6 else kwargs.pop("cancel_url"),
        **kwargs,
    )


async def _capture_paypal_order(order_id):
    return await capture_paypal_order(
        client_id=PAYPAL_CLIENT_ID,
        secret=PAYPAL_SECRET,
        api_url=PAYPAL_API_URL,
        safe_amount=_safe_amount_with_fallback,
        zero_decimal_currencies=ZERO_DECIMAL_CURRENCIES,
        order_id=order_id,
    )


async def _verify_paypal_webhook(request, raw_body):
    if not PAYPAL_WEBHOOK_ID:
        logger.warning("PayPal webhook ID not configured, skipping verification")
        return True
    return await verify_paypal_webhook(
        client_id=PAYPAL_CLIENT_ID,
        secret=PAYPAL_SECRET,
        api_url=PAYPAL_API_URL,
        request=request,
        raw_body=raw_body,
    )


# Shared checkout constants and helpers live in payments_checkout_core.py.
SUPPORTED_CURRENCIES = _checkout_core.SUPPORTED_CURRENCIES
ZERO_DECIMAL_CURRENCIES = _checkout_core.ZERO_DECIMAL_CURRENCIES
PAYPAL_SUPPORTED_CURRENCIES = _checkout_core.PAYPAL_SUPPORTED_CURRENCIES
_fx_last_updated = _checkout_core._fx_last_updated
_safe_float = _checkout_core._safe_float
_resolve_jurisdiction = _checkout_core._resolve_jurisdiction
_extract_tx_financials = _checkout_core._extract_tx_financials
_normalize_zero_decimal_checkout_amounts = _checkout_core._normalize_zero_decimal_checkout_amounts
_detect_locale = _checkout_core._detect_locale
_is_french_context = _checkout_core._is_french_context
_receipt_product_type_label = _checkout_core._receipt_product_type_label
_currency_symbol_for = _checkout_core._currency_symbol_for
_fx_rate_for = _checkout_core._fx_rate_for
_convert_from_usd = _checkout_core._convert_from_usd
_minutes_since_iso = _checkout_core._minutes_since_iso
_compute_checkout_breakdown = _checkout_core._compute_checkout_breakdown


async def refresh_fx_rates():
    """Fetch live FX rates from open API and update SUPPORTED_CURRENCIES."""
    global _fx_last_updated
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("result") == "success":
                    rates = data.get("rates", {})
                    updated = 0
                    for code in SUPPORTED_CURRENCIES:
                        if code in rates and code != "USD":
                            SUPPORTED_CURRENCIES[code]["rate"] = round(rates[code], 4)
                            updated += 1
                    _fx_last_updated = data.get("time_last_update_utc", "")
                    logger.info(f"FX rates updated: {updated} currencies from open.er-api.com")
                    return True
    except Exception as e:
        logger.warning(f"FX rate refresh failed (using fallback rates): {e}")
    return False


@router.on_event("startup")
async def _init_fx_rates():
    """Fetch live FX rates on startup."""
    await refresh_fx_rates()


@router.get("/payments/fx/refresh")
async def manual_fx_refresh():
    """Manually trigger FX rate refresh (admin use)."""
    success = await refresh_fx_rates()
    return {"refreshed": success, "last_updated": _fx_last_updated}


@router.get("/payments/currencies")
async def get_supported_currencies():
    """Return list of supported currencies with symbols and approximate FX rates."""
    currencies = []
    for code, info in SUPPORTED_CURRENCIES.items():
        currencies.append({
            "code": code,
            "symbol": info["symbol"],
            "name": info["name"],
            "rate": info["rate"],
            "stripe_supported": info["stripe_supported"],
        })
    return {"currencies": currencies, "base_currency": "USD"}


@router.get("/payments/config")
async def get_payment_config(request: Request):
    """Return payment provider availability and configuration.
    Public: only publishable keys and availability flags.
    Authenticated: full gateway status details."""
    from routes.db import get_current_user

    fedapay_secret = os.environ.get("FEDAPAY_SECRET_KEY")
    fedapay_public_key = os.environ.get("FEDAPAY_PUBLIC_KEY", "")
    stripe_publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

    from routes.iap import _resolve_iap_provider_readiness

    stripe_secret_key = STRIPE_API_KEY or ""
    stripe_available = bool(stripe_secret_key)
    paypal_available = bool(PAYPAL_CLIENT_ID and PAYPAL_SECRET)

    if stripe_secret_key.startswith("sk_live_") or stripe_publishable_key.startswith("pk_live_"):
        stripe_mode = "live"
    elif stripe_secret_key.startswith("sk_test_") or stripe_publishable_key.startswith("pk_test_"):
        stripe_mode = "test"
    else:
        stripe_mode = "unknown"

    fedapay_available = bool(fedapay_secret and fedapay_public_key)

    if (fedapay_secret or "").startswith("sk_live_") or fedapay_public_key.startswith("pk_live_"):
        fedapay_mode = "live"
    elif (
        (fedapay_secret or "").startswith("sk_test_")
        or fedapay_public_key.startswith("pk_test_")
        or "sandbox" in str(fedapay_secret or "").lower()
        or "sandbox" in fedapay_public_key.lower()
    ):
        fedapay_mode = "test"
    else:
        fedapay_mode = "unknown"

    stripe_status_label = "Live Ready" if stripe_available and stripe_mode == "live" else "Test Ready" if stripe_available else "Unavailable"
    paypal_status_label = "Live Ready" if paypal_available and PAYPAL_MODE == "live" else "Sandbox Ready" if paypal_available else "Unavailable"
    fedapay_status_label = "Live Ready" if fedapay_available and fedapay_mode == "live" else "Test Ready" if fedapay_available and fedapay_mode == "test" else "Unavailable" if not fedapay_available else "Configured"

    iap_readiness = _resolve_iap_provider_readiness()
    apple_row = (iap_readiness.get("providers") or {}).get("apple") or {}
    google_row = (iap_readiness.get("providers") or {}).get("google") or {}

    # Detect currency from Accept-Language header or query param
    preferred_currency = request.query_params.get("currency", "USD").upper()
    if preferred_currency not in SUPPORTED_CURRENCIES:
        preferred_currency = "USD"

    # Base public payload — only what's needed for client-side SDK init
    payload = {
        "stripe_available": stripe_available,
        "stripe_publishable_key": stripe_publishable_key,
        "paypal_available": paypal_available,
        "paypal_client_id": PAYPAL_CLIENT_ID or "",
        "paypal_mode": PAYPAL_MODE,
        "fedapay_available": fedapay_available,
        "fedapay_public_key": fedapay_public_key,
        "apple_iap_available": bool(apple_row.get("configured") or apple_row.get("sandbox_probe_configured")),
        "google_iap_available": bool(google_row.get("configured") or google_row.get("sandbox_probe_configured")),
        "apple_iap_status_label": apple_row.get("status_label", "Unavailable"),
        "google_iap_status_label": google_row.get("status_label", "Unavailable"),
        "currency": preferred_currency,
        "currency_symbol": SUPPORTED_CURRENCIES[preferred_currency]["symbol"],
        "fx_rate": SUPPORTED_CURRENCIES[preferred_currency]["rate"],
        "brand_name": BRAND_NAME,
        "supported_currencies": list(SUPPORTED_CURRENCIES.keys()),
    }

    # Authenticated users get full gateway status details
    user = None
    try:
        user = await get_current_user(request)
    except Exception:
        pass
    if user:
        payload["stripe_mode"] = stripe_mode
        payload["stripe_status_label"] = stripe_status_label
        payload["stripe_live_ready"] = bool(stripe_available and stripe_mode == "live" and stripe_publishable_key.startswith("pk_live_"))
        payload["paypal_status_label"] = paypal_status_label
        payload["paypal_live_ready"] = bool(paypal_available and PAYPAL_MODE == "live")
        payload["fedapay_mode"] = fedapay_mode
        payload["fedapay_status_label"] = fedapay_status_label
        payload["fedapay_live_ready"] = bool(fedapay_available and fedapay_mode == "live")
        payload["apple_iap_mode"] = apple_row.get("mode", "live")
        payload["google_iap_mode"] = google_row.get("mode", "live")
        payload["apple_iap_live_ready"] = bool(apple_row.get("readiness_state") == "live_ready")
        payload["google_iap_live_ready"] = bool(google_row.get("readiness_state") == "live_ready")
        payload["email_service_available"] = bool(is_email_configured())

    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/subscriptions/gateway-config")
async def get_subscription_gateway_config(request: Request):
    """Backward-compatible alias for gateway/provider configuration."""
    return await get_payment_config(request)


@router.get("/subscriptions/provider-readiness-matrix")
async def get_provider_readiness_matrix(request: Request):
    """Unified readiness matrix for all supported subscription payment providers."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    cfg_response = await get_payment_config(request)
    cfg: Dict[str, Any] = {}
    try:
        if isinstance(cfg_response, JSONResponse):
            cfg = json.loads((cfg_response.body or b"{}").decode("utf-8"))
        elif isinstance(cfg_response, dict):
            cfg = cfg_response
    except Exception:
        cfg = {}
    return {
        "providers": {
            "stripe": {
                "available": bool(cfg.get("stripe_available")),
                "status_label": cfg.get("stripe_status_label", "Unavailable"),
                "live_ready": bool(cfg.get("stripe_live_ready")),
                "action": "redirect_url",
                "route": "/subscription/payment",
            },
            "paypal": {
                "available": bool(cfg.get("paypal_available")),
                "status_label": cfg.get("paypal_status_label", "Unavailable"),
                "live_ready": bool(cfg.get("paypal_live_ready")),
                "action": "redirect_url",
                "route": "/subscription/payment",
            },
            "fedapay": {
                "available": bool(cfg.get("fedapay_available")),
                "status_label": cfg.get("fedapay_status_label", "Unavailable"),
                "live_ready": bool(cfg.get("fedapay_live_ready")),
                "action": "route",
                "route": "/subscription/mobile-money",
            },
            "apple_iap": {
                "available": bool(cfg.get("apple_iap_available")),
                "status_label": cfg.get("apple_iap_status_label", "Unavailable"),
                "live_ready": bool(cfg.get("apple_iap_live_ready")),
                "action": "route",
                "route": "/subscription/mobile",
            },
            "google_iap": {
                "available": bool(cfg.get("google_iap_available")),
                "status_label": cfg.get("google_iap_status_label", "Unavailable"),
                "live_ready": bool(cfg.get("google_iap_live_ready")),
                "action": "route",
                "route": "/subscription/mobile",
            },
        }
    }


@router.get("/admin/subscriptions/provider-drilldown")
async def get_provider_drilldown(request: Request, days: int = 7):
    """Operational drilldown for provider reliability and checkout edge failures."""
    await require_admin(request)
    window_days = max(1, min(int(days or 7), 60))
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    since_iso = since.isoformat()

    providers = ["stripe", "paypal", "fedapay", "apple_iap", "google_iap"]
    rows: Dict[str, Dict[str, Any]] = {}
    for provider in providers:
        rows[provider] = {
            "provider": provider,
            "transactions_total": 0,
            "completed": 0,
            "pending": 0,
            "failed": 0,
            "checkout_init_failures": 0,
            "edge_abort_failures": 0,
            "edge_challenge_failures": 0,
        }

    tx_query = {"created_at": {"$gte": since_iso}}
    async for tx in iter_find_paginated(
        db.payment_transactions,
        tx_query,
        {"_id": 0, "provider": 1, "payment_method": 1, "payment_status": 1},
        max_docs=10000,
    ):
        provider = _normalize_trust_provider(str(tx.get("provider") or tx.get("payment_method") or ""))
        if provider not in rows:
            if str(tx.get("payment_method") or "") in {"apple_iap", "google_iap"}:
                provider = str(tx.get("payment_method"))
            else:
                continue
        rows[provider]["transactions_total"] += 1
        status = str(tx.get("payment_status") or "").lower()
        if status in {"completed", "paid", "succeeded"}:
            rows[provider]["completed"] += 1
        elif status in {"failed", "cancelled", "declined"}:
            rows[provider]["failed"] += 1
        else:
            rows[provider]["pending"] += 1

    async for event in iter_find_paginated(
        db.subscription_checkout_frontend_events,
        {"created_at": {"$gte": since_iso}},
        {"_id": 0, "payment_method": 1, "reason": 1},
        max_docs=10000,
    ):
        provider = normalize_payment_method(event.get("payment_method"))
        if provider == "card":
            provider = "stripe"
        if provider not in rows:
            continue
        rows[provider]["checkout_init_failures"] += 1
        reason = str(event.get("reason") or "").lower()
        if "network_or_edge_abort" in reason:
            rows[provider]["edge_abort_failures"] += 1
        if "edge_challenge" in reason or "auth_or_edge_blocked" in reason:
            rows[provider]["edge_challenge_failures"] += 1

    for provider in providers:
        total = rows[provider]["transactions_total"]
        rows[provider]["success_rate"] = round((rows[provider]["completed"] / total) * 100, 2) if total else 0.0

    return {
        "window_days": window_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "providers": [rows[p] for p in providers],
    }


# ── Helper: get authenticated user ──
async def _get_user_from_request(request: Request, token_override: Optional[str] = None):
    from .db import JWT_SECRET
    import jwt

    auth = request.headers.get("Authorization", "")
    token = token_override or getattr(request.state, "token_override", None) or ""
    if not token:
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else request.cookies.get("session_token", "")
    # Also check query param for document downloads opened in new tabs
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        token = request.query_params.get("t", "")
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_doc = await db.users.find_one({"user_id": payload.get("user_id")}, {"_id": 0})
        if user_doc:
            return type("User", (), user_doc)()
        return None
    except Exception:
        return None


async def _require_auth_payment(request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


_payment_card_routes.configure_payment_card_routes(
    get_user_from_request=_get_user_from_request,
    stripe_api_key=STRIPE_API_KEY,
    logger=logger,
)
router.include_router(_payment_card_routes.router)
add_payment_card = _payment_card_routes.add_payment_card
list_payment_cards = _payment_card_routes.list_payment_cards
list_checkout_ready_cards = _payment_card_routes.list_checkout_ready_cards
update_payment_card = _payment_card_routes.update_payment_card
delete_payment_card = _payment_card_routes.delete_payment_card
set_default_card = _payment_card_routes.set_default_card

_reporting_routes.configure_payment_reporting_routes(
    get_user_from_request=_get_user_from_request,
    route_logger=logger,
)
router.include_router(_reporting_routes.router)
get_report_preferences = _reporting_routes.get_report_preferences
update_report_preferences = _reporting_routes.update_report_preferences
send_report_now = _reporting_routes.send_report_now
generate_and_send_payment_report = _reporting_routes.generate_and_send_payment_report
run_scheduled_payment_reports = _reporting_routes.run_scheduled_payment_reports
export_payment_history_pdf = _reporting_routes.export_payment_history_pdf
export_payment_history_csv = _reporting_routes.export_payment_history_csv
_fetch_payment_history_export_items = _reporting_routes._fetch_payment_history_export_items
_build_payment_history_csv_text = _reporting_routes._build_payment_history_csv_text
_get_payment_history_export_settings = _reporting_routes._get_payment_history_export_settings
_PAYMENT_REPORT_TEMPLATE_WIRING = (
    'template_key="payment_report"',
    "report_type=",
    "period_desc=",
    "plan_name=",
    "total_period=",
    "total_alltime=",
)


async def _send_payment_notification_proxy(**kwargs):
    return await _send_payment_notification(**kwargs)


async def _send_user_payment_failure_recovery_email_proxy(**kwargs):
    return await _send_user_payment_failure_recovery_email(**kwargs)


async def _send_admin_payment_failure_alert_proxy(**kwargs):
    return await _send_admin_payment_failure_alert(**kwargs)


_recovery_routes.configure_payment_recovery_routes(
    get_user_from_request=_get_user_from_request,
    send_payment_notification=_send_payment_notification_proxy,
    route_logger=logger,
)
router.include_router(_recovery_routes.router)
_queue_payment_notification_recovery = _recovery_routes.queue_payment_notification_recovery
_mark_payment_notification_sent = _recovery_routes.mark_payment_notification_sent
_should_suppress_payment_notifications = _recovery_routes.should_suppress_payment_notifications
_build_missed_notification_recovery_query = _recovery_routes.build_missed_notification_recovery_query
_recover_missed_notification_for_transaction = _recovery_routes.recover_missed_notification_for_transaction
recover_missed_payment_notifications = _recovery_routes.recover_missed_payment_notifications


# Payment locale detection lives in utils.payment_localization.detect_payment_locale.


_stripe_routes.configure_stripe_routes(
    stripe_api_key=STRIPE_API_KEY or "",
    stripe_webhook_secret=STRIPE_WEBHOOK_SECRET or "",
    zero_decimal_currencies=ZERO_DECIMAL_CURRENCIES,
    get_subscription_lifecycle_state=lambda user_id: _get_subscription_lifecycle_state(user_id),
    build_payment_record_from_tx=lambda *args, **kwargs: _build_payment_record_from_tx(*args, **kwargs),
    extract_tx_financials=_extract_tx_financials,
    send_payment_notification=_send_payment_notification_proxy,
    mark_payment_notification_sent=_mark_payment_notification_sent,
    queue_payment_notification_recovery=_queue_payment_notification_recovery,
    send_user_payment_failure_recovery_email=_send_user_payment_failure_recovery_email_proxy,
    send_admin_payment_failure_alert=_send_admin_payment_failure_alert_proxy,
    compute_checkout_breakdown=_compute_checkout_breakdown,
    checkout_preview_request=CheckoutPreviewRequest,
    safe_float=_safe_float,
    fx_rate_for=_fx_rate_for,
    route_logger=logger,
)
router.include_router(_stripe_routes.router)
get_checkout_status = _stripe_routes.get_checkout_status
stripe_webhook = _stripe_routes.stripe_webhook
_fetch_stripe_session_financials = _stripe_routes._fetch_stripe_session_financials
_merge_stripe_provider_financials = _stripe_routes._merge_stripe_provider_financials
_create_stripe_checkout_response = _stripe_routes.create_stripe_checkout_response


async def _send_payment_email_proxy(**kwargs):
    return await _send_payment_email(**kwargs)


_history_routes.configure_payment_history_routes(
    get_user_from_request=_get_user_from_request,
    send_payment_email=_send_payment_email_proxy,
    safe_float=_safe_float,
)
router.include_router(_history_routes.router)
get_payment_history = _history_routes.get_payment_history
get_receipt_transparency_mode = _history_routes.get_receipt_transparency_mode
set_receipt_transparency_mode = _history_routes.set_receipt_transparency_mode
download_tax_statement_csv = _history_routes.download_tax_statement_csv
download_tax_statement_pdf = _history_routes.download_tax_statement_pdf
tax_ready_csv_export = _history_routes.tax_ready_csv_export
get_invoice = _history_routes.get_invoice
get_receipt = _history_routes.get_receipt
verify_document = _history_routes.verify_document
verify_export_integrity = _history_routes.verify_export_integrity
send_verified_receipt_email = _history_routes.send_verified_receipt_email
get_receipt_csv = _history_routes.get_receipt_csv
get_invoice_csv = _history_routes.get_invoice_csv
get_receipt_pdf = _history_routes.get_receipt_pdf
get_invoice_pdf = _history_routes.get_invoice_pdf
email_receipt = _history_routes.email_receipt
email_invoice = _history_routes.email_invoice
bulk_export_receipts = _history_routes.bulk_export_receipts
bulk_all_receipts = _history_routes.bulk_all_receipts
download_all_receipts_pdf_csv_bundle = _history_routes.download_all_receipts_pdf_csv_bundle
email_yearly_receipt_summary = _history_routes.email_yearly_receipt_summary
_parse_statement_scope = _history_routes._parse_statement_scope
_build_tax_statement_csv_text = _history_routes._build_tax_statement_csv_text
_generate_tax_statement_pdf = _history_routes._generate_tax_statement_pdf
_payment_from_txn = _history_routes._payment_from_txn
_alert_missing_tax_fields = _history_routes._alert_missing_tax_fields
_get_receipt_transparency_mode = _history_routes._get_receipt_transparency_mode
_missing_tax_fields = _history_routes._missing_tax_fields
_find_payment_record = _history_routes._find_payment_record
_generate_document_html = _history_routes._generate_document_html
_generate_pdf_from_payment = _history_routes._generate_pdf_from_payment
_format_payment_method_label = _history_routes._format_payment_method_label
_format_payment_status_label = _history_routes._format_payment_status_label
_build_single_document_csv_text = _history_routes._build_single_document_csv_text
_fetch_all_receipts_records_for_user = _history_routes._fetch_all_receipts_records_for_user
_generate_combined_receipts_single_pass = _history_routes._generate_combined_receipts_single_pass

_user_analytics_routes.configure_payment_user_analytics_routes(
    get_user_from_request=_get_user_from_request,
)
router.include_router(_user_analytics_routes.router)
my_payment_analytics = _user_analytics_routes.my_payment_analytics

_admin_maintenance_routes.configure_payment_admin_maintenance_routes(
    get_user_from_request=_get_user_from_request,
    safe_float=_safe_float,
    extract_tx_financials=_extract_tx_financials,
)
router.include_router(_admin_maintenance_routes.router)
trigger_renewal_reminders = _admin_maintenance_routes.trigger_renewal_reminders
run_renewal_reminder_check = _admin_maintenance_routes.run_renewal_reminder_check
download_monthly_executive_billing_pack = _admin_maintenance_routes.download_monthly_executive_billing_pack
get_payment_history_export_settings = _admin_maintenance_routes.get_payment_history_export_settings
update_payment_history_export_settings = _admin_maintenance_routes.update_payment_history_export_settings
reset_payment_history_export_settings = _admin_maintenance_routes.reset_payment_history_export_settings
verify_payment_history_export_integrity = _admin_maintenance_routes.verify_payment_history_export_integrity
PaymentHistoryExportSettingsUpdate = _admin_maintenance_routes.PaymentHistoryExportSettingsUpdate
PaymentHistoryIntegrityVerifyRequest = _admin_maintenance_routes.PaymentHistoryIntegrityVerifyRequest
RECEIPT_BRANDING_DEFAULTS = _admin_maintenance_routes.RECEIPT_BRANDING_DEFAULTS
get_receipt_branding = _admin_maintenance_routes.get_receipt_branding
ReceiptBrandingUpdate = _admin_maintenance_routes.ReceiptBrandingUpdate
update_receipt_branding = _admin_maintenance_routes.update_receipt_branding
reset_receipt_branding = _admin_maintenance_routes.reset_receipt_branding
preview_receipt_branding = _admin_maintenance_routes.preview_receipt_branding
CUSTOM_LOGO_DIR = _admin_maintenance_routes.CUSTOM_LOGO_DIR
upload_receipt_logo = _admin_maintenance_routes.upload_receipt_logo
delete_receipt_logo = _admin_maintenance_routes.delete_receipt_logo
recovery_stats = _admin_maintenance_routes.recovery_stats
run_tax_compliance_audit = _admin_maintenance_routes.run_tax_compliance_audit

_document_proxy_routes.configure_payment_document_proxy_routes(
    get_user_from_request=_get_user_from_request,
    brand_name=BRAND_NAME,
)
router.include_router(_document_proxy_routes.router)
docs_report = _document_proxy_routes.docs_report
docs_data = _document_proxy_routes.docs_data
content_document = _document_proxy_routes.content_document
content_retrieve = _document_proxy_routes.content_retrieve
content_export = _document_proxy_routes.content_export
asset_file = _document_proxy_routes.asset_file
asset_export = _document_proxy_routes.asset_export
relay_file = _document_proxy_routes.relay_file
relay_export = _document_proxy_routes.relay_export
relay_document_view = _document_proxy_routes.relay_document_view
relay_history_tool = _document_proxy_routes.relay_history_tool


_paypal_routes.configure_paypal_routes(
    get_user_from_request=_get_user_from_request,
    resolve_saved_card_for_checkout=_resolve_saved_card_for_checkout,
    compute_checkout_breakdown=_compute_checkout_breakdown,
    checkout_preview_request=CheckoutPreviewRequest,
    get_paypal_token=_get_paypal_token,
    capture_paypal_order=_capture_paypal_order,
    verify_paypal_webhook=_verify_paypal_webhook,
    get_subscription_lifecycle_state=lambda user_id: _get_subscription_lifecycle_state(user_id),
    build_payment_record_from_tx=lambda *args, **kwargs: _build_payment_record_from_tx(*args, **kwargs),
    send_payment_notification=_send_payment_notification_proxy,
    mark_payment_notification_sent=_mark_payment_notification_sent,
    queue_payment_notification_recovery=_queue_payment_notification_recovery,
    send_user_payment_failure_recovery_email=_send_user_payment_failure_recovery_email_proxy,
    send_admin_payment_failure_alert=_send_admin_payment_failure_alert_proxy,
    fx_rate_for=_fx_rate_for,
    safe_float=_safe_float,
    paypal_client_id=PAYPAL_CLIENT_ID or "",
    paypal_api_url=PAYPAL_API_URL,
    paypal_supported_currencies=PAYPAL_SUPPORTED_CURRENCIES,
    zero_decimal_currencies=ZERO_DECIMAL_CURRENCIES,
    route_logger=logger,
)
router.include_router(_paypal_routes.router)
get_paypal_client_id = _paypal_routes.get_paypal_client_id
paypal_create_order = _paypal_routes.paypal_create_order
paypal_capture_order = _paypal_routes.paypal_capture_order
paypal_webhook = _paypal_routes.paypal_webhook

_fedapay_routes.configure_fedapay_routes(
    get_user_from_request=_get_user_from_request,
    resolve_saved_card_for_checkout=_resolve_saved_card_for_checkout,
    compute_checkout_breakdown=_compute_checkout_breakdown,
    checkout_preview_request=CheckoutPreviewRequest,
    get_subscription_lifecycle_state=lambda user_id: _get_subscription_lifecycle_state(user_id),
    build_payment_record_from_tx=lambda *args, **kwargs: _build_payment_record_from_tx(*args, **kwargs),
    send_payment_notification=_send_payment_notification_proxy,
    send_user_payment_failure_recovery_email=_send_user_payment_failure_recovery_email_proxy,
    send_admin_payment_failure_alert=_send_admin_payment_failure_alert_proxy,
    safe_float=_safe_float,
    minutes_since_iso=_minutes_since_iso,
    lock_single_payment_communication=LOCK_SINGLE_PAYMENT_COMMUNICATION,
    route_logger=logger,
)
router.include_router(_fedapay_routes.router)


def _build_checkout_transition(state: str, source: str, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "state": str(state or "unknown"),
        "source": str(source or "checkout"),
        "detail": str(detail or "")[:300],
        "meta": meta or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _append_checkout_transition(tx_filter: Dict[str, Any], state: str, source: str, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
    if not tx_filter:
        return
    transition = _build_checkout_transition(state, source, detail, meta)
    await db.payment_transactions.update_one(
        tx_filter,
        {
            "$set": {
                "checkout_state": transition["state"],
                "checkout_state_updated_at": transition["created_at"],
                "updated_at": transition["created_at"],
            },
            "$push": {
                "checkout_state_history": {
                    "$each": [transition],
                    "$slice": -40,
                }
            },
        },
    )
get_mobile_money_gateways = _fedapay_routes.get_mobile_money_gateways
get_fedapay_policy_view = _fedapay_routes.get_fedapay_policy_view
admin_refresh_fedapay_policy = _fedapay_routes.admin_refresh_fedapay_policy
get_fedapay_policy_timeline = _fedapay_routes.get_fedapay_policy_timeline
get_sandbox_info = _fedapay_routes.get_sandbox_info
MobileMoneySubscriptionRequest = _fedapay_routes.MobileMoneySubscriptionRequest
mobile_money_subscription = _fedapay_routes.mobile_money_subscription
fedapay_webhook_health = _fedapay_routes.fedapay_webhook_health
fedapay_webhook_info = _fedapay_routes.fedapay_webhook_info
fedapay_webhook = _fedapay_routes.fedapay_webhook
fedapay_webhook_ack = _fedapay_routes.fedapay_webhook_ack
fedapay_payment_status = _fedapay_routes.fedapay_payment_status
fedapay_callback = _fedapay_routes.fedapay_callback
run_fedapay_webhook_retry_cycle = _fedapay_routes.run_fedapay_webhook_retry_cycle
run_fedapay_webhook_dead_replay_cycle = _fedapay_routes.run_fedapay_webhook_dead_replay_cycle
_extract_fedapay_entity = _fedapay_routes._extract_fedapay_entity
_build_fedapay_webhook_event_key = _fedapay_routes._build_fedapay_webhook_event_key
_queue_fedapay_webhook_event = _fedapay_routes._queue_fedapay_webhook_event
_apply_fedapay_webhook_payload = _fedapay_routes._apply_fedapay_webhook_payload
_process_fedapay_webhook_event = _fedapay_routes._process_fedapay_webhook_event
_ingest_fedapay_webhook_async = _fedapay_routes._ingest_fedapay_webhook_async
_ack_fedapay_webhook_request = _fedapay_routes._ack_fedapay_webhook_request


# Stripe provider financial helpers live in payments_stripe_routes.py.

def _build_payment_record_from_tx(tx: Dict[str, Any], *, status: str = "completed") -> Dict[str, Any]:
    financials = _extract_tx_financials(tx)
    created_at = tx.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            created_at = datetime.now(timezone.utc)
    if not isinstance(created_at, datetime):
        created_at = datetime.now(timezone.utc)

    return PaymentRecord(
        user_id=tx.get("user_id", ""),
        plan_id=tx.get("plan_id", ""),
        amount=_safe_float(tx.get("amount", tx.get("amount_usd", 0)), 0.0),
        currency=str(tx.get("currency", "usd")),
        payment_method=tx.get("payment_method", ""),
        payment_id=tx.get("payment_id") or tx.get("session_id") or tx.get("transaction_id") or "",
        status=status,
        subtotal=financials["subtotal"],
        tax_amount=financials["tax_amount"],
        processing_fee=financials["processing_fee"],
        amount_gross=financials["amount_gross"],
        amount_net=financials["amount_net"],
        total_amount=financials["total_amount"],
        provider=str(tx.get("provider", tx.get("gateway", tx.get("payment_method", "")))),
        transaction_id=tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id") or "",
        jurisdiction=tx.get("jurisdiction", {}),
        product_type=tx.get("product_type", "education_digital_service"),
        tax_provider=tx.get("tax_provider", "internal_rules_engine"),
        tax_rate=_safe_float(tx.get("tax_rate", 0), 0.0),
        tax_breakdown=tx.get("tax_breakdown", []),
        locale=_detect_locale(tx),
        preferred_language=normalize_language_code(tx.get("preferred_language", "")) or _detect_locale(tx),
        localization_context=tx.get("localization_context", {}) if isinstance(tx.get("localization_context"), dict) else {},
        fx_rate=_safe_float(tx.get("fx_rate", 1.0), 1.0),
        fx_base_currency=str(tx.get("fx_base_currency", "USD") or "USD").upper(),
        original_usd_amount=_safe_float(tx.get("original_usd_amount", tx.get("amount_usd", tx.get("amount", 0))), 0.0),
        created_at=created_at,
    ).dict()


# ── Email confirmation via Resend-backed email service ──
def _build_payment_email_html(
    plan_name: str, amount: float, payment_method: str, ticket_id: str, user_name: str
) -> str:
    method_label = _format_payment_method_label(payment_method)
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; background: #0B0F1A; padding: 40px 16px;">
      <div style="background: #111827; border-radius: 20px; border: 1px solid #1E293B; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #0ea5e9, #6366f1); padding: 36px 32px; text-align: center;">
          <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 800;">Payment Confirmed</h1>
          <p style="color: rgba(255,255,255,0.7); margin: 8px 0 0; font-size: 13px;">RealAICoach &middot; Secure billing</p>
        </div>
        <div style="padding: 32px;">
          <p style="color: #F8FAFC; font-size: 16px; margin: 0 0 24px;">Hi {user_name},</p>
          <p style="color: #CBD5E1; font-size: 14px; line-height: 1.6; margin: 0 0 24px;">
            Your payment has been successfully processed. Here are your receipt details:
          </p>
          <div style="background: #0F172A; border-radius: 12px; padding: 0; border: 1px solid #1E293B; margin-bottom: 24px; overflow: hidden;">
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="padding: 12px 16px; color: #64748B; font-size: 13px; border-bottom: 1px solid #1E293B;">Plan</td>
                <td style="padding: 12px 16px; color: #F8FAFC; font-size: 13px; text-align: right; font-weight: 600; border-bottom: 1px solid #1E293B;">{plan_name}</td>
              </tr>
              <tr>
                <td style="padding: 12px 16px; color: #64748B; font-size: 13px; border-bottom: 1px solid #1E293B;">Amount</td>
                <td style="padding: 12px 16px; color: #10B981; font-size: 13px; text-align: right; font-weight: 600; border-bottom: 1px solid #1E293B;">${amount:.2f}</td>
              </tr>
              <tr>
                <td style="padding: 12px 16px; color: #64748B; font-size: 13px; border-bottom: 1px solid #1E293B;">Payment Method</td>
                <td style="padding: 12px 16px; color: #F8FAFC; font-size: 13px; text-align: right; font-weight: 600; border-bottom: 1px solid #1E293B;">{method_label}</td>
              </tr>
              <tr>
                <td style="padding: 12px 16px; color: #64748B; font-size: 13px;">eTicket</td>
                <td style="padding: 12px 16px; color: #6366f1; font-size: 13px; text-align: right; font-weight: 600;">{ticket_id}</td>
              </tr>
            </table>
          </div>
          <div style="background: #10B98118; border-radius: 10px; padding: 14px 18px; border-left: 3px solid #10B981; margin-bottom: 24px;">
            <p style="color: #10B981; font-size: 13px; margin: 0;">
              Your {plan_name} plan is now active. Enjoy all the premium features!
            </p>
          </div>
          <p style="color: #475569; font-size: 12px; text-align: center; margin: 0;">
            If you have questions, contact us at support@realaicoach.app
          </p>
        </div>
        <div style="text-align: center; padding: 20px 32px; border-top: 1px solid #1E293B;">
          <p style="color: #334155; font-size: 11px; margin: 0;">&copy; RealAICoach 2026-2030. All rights reserved. (USA)</p>
        </div>
      </div>
    </div>
    """


# LOCKED: Canonical admin email for all admin alerts — do not change.
_LOCKED_ADMIN_EMAIL = "admin@realaicoach.app"


async def _get_subscription_lifecycle_state(user_id: str) -> Dict[str, Any]:
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "pending_subscription_transition": 1},
    ) or {}
    pending = user_doc.get("pending_subscription_transition") or {}
    return {
        "previous_plan": str(user_doc.get("subscription_plan") or "free"),
        "previous_status": str(user_doc.get("subscription_status") or "free"),
        "pending_action": str(pending.get("action") or ""),
    }


def _is_subscription_restoration(context: Optional[Dict[str, Any]]) -> bool:
    context = context or {}
    prev_status = str(context.get("previous_status") or "").lower()
    pending_action = str(context.get("pending_action") or "").lower()
    return prev_status in {"expired", "cancelled"} or pending_action == "cancel"
ADMIN_FAILURE_ALERT_EMAIL_ENABLED = str(
    os.environ.get("ADMIN_FAILURE_ALERT_EMAIL_ENABLED", "false")
).strip().lower() in {"1", "true", "yes", "on"}


async def _get_admin_receipt_recipients(exclude_email: str = "") -> list[str]:
    candidate_recipients: list[str] = [_LOCKED_ADMIN_EMAIL]

    for env_key in ["ADMIN_EMAIL", "ADMIN_ALERT_EMAIL", "FINANCE_ALERT_EMAILS", "ADMIN_NOTIFICATION_EMAILS"]:
        raw = (os.environ.get(env_key, "") or "").strip()
        if not raw:
            continue
        for item in raw.replace(";", ",").split(","):
            candidate = item.strip().lower()
            if candidate and "@" in candidate:
                candidate_recipients.append(candidate)

    try:
        admins = await db.users.find(
            {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        ).limit(25).to_list(25)
        for admin in admins:
            candidate = str(admin.get("email", "")).strip().lower()
            if candidate and "@" in candidate:
                candidate_recipients.append(candidate)
    except Exception as exc:
        logger.warning(f"Failed loading admin recipients from DB: {exc}")

    excluded = (exclude_email or "").strip().lower()
    seen: set[str] = set()
    for candidate in candidate_recipients:
        if not candidate or candidate == excluded or candidate in seen:
            continue
        seen.add(candidate)
        return [candidate]

    return []


async def _create_admin_payment_alert_notification(
    *,
    customer_email: str,
    customer_name: str,
    plan_name: str,
    payment_method: str,
    ticket_id: str,
    billing_cycle: str,
    amount: float,
    amount_local: float,
    currency: str,
    transaction_context: Optional[Dict[str, Any]] = None,
):
    """Create in-app admin alert notification for successful payment confirmations."""
    created_ids: list[str] = []
    try:
        admin_targets = await _get_admin_receipt_recipients(exclude_email=customer_email)
        if not admin_targets:
            return created_ids

        admin_users = await db.users.find(
            {"email": {"$in": admin_targets}},
            {"_id": 0, "user_id": 1, "email": 1},
        ).limit(50).to_list(50)

        if not admin_users:
            return

        amount_display = f"{amount_local:,.2f} {currency}" if amount_local and currency and currency.upper() != "USD" else f"${amount:.2f}"
        method_label = _format_payment_method_label(
            _normalize_payment_method_for_display(payment_method, transaction_context)
        )
        for admin_user in admin_users:
            admin_user_id = admin_user.get("user_id")
            if not admin_user_id:
                continue

            admin_notif_id = f"notif_{uuid.uuid4().hex[:12]}"

            admin_notif = {
                "id": admin_notif_id,
                "notification_id": admin_notif_id,
                "user_id": admin_user_id,
                "type": "admin_payment_alert",
                "title": "Admin Alert - Payment Confirmed",
                "message": (
                    f"{customer_name or customer_email} completed {plan_name} ({billing_cycle}) via "
                    f"{method_label}. Amount: {amount_display}. Ticket: {ticket_id}"
                ),
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "customer_email": customer_email,
                    "plan": plan_name,
                    "billing_cycle": billing_cycle,
                    "payment_method": payment_method,
                    "ticket_id": ticket_id,
                    "amount": amount,
                    "amount_local": amount_local,
                    "currency": currency,
                },
            }
            await db.notifications.insert_one({**admin_notif})
            await _push_realtime_notification(admin_user_id, admin_notif)
            created_ids.append(admin_notif_id)
    except Exception as exc:
        logger.warning(f"Admin in-app payment alert creation failed: {exc}")
    return created_ids


async def _push_realtime_notification(user_id: str, notification: Dict[str, Any]) -> None:
    """Push a freshly created notification over WebSocket and trigger notification refresh."""
    try:
        from utils.ws_manager import ws_manager, broadcast_data_change

        unread = await db.notifications.count_documents({"user_id": user_id, "read": False})
        await ws_manager.send_to_user(
            user_id,
            {
                "type": "notification",
                "notification": notification,
                "unread_count": unread,
            },
        )
        await broadcast_data_change(
            "notifications",
            "created",
            user_id,
            extra={
                "notification_id": notification.get("notification_id") or notification.get("id"),
                "notification_type": notification.get("type"),
            },
        )
    except Exception as exc:
        logger.warning(f"Realtime notification push failed for {user_id}: {exc}")


# Payment notification recovery helpers live in payments_recovery_routes.py.


def _normalize_payment_method_for_display(method_raw: str, tx: Optional[Dict[str, Any]] = None) -> str:
    tx = tx or {}
    method = str(method_raw or "card").strip().lower()
    provider = str(tx.get("provider") or tx.get("gateway") or "").strip().lower()

    if "fedapay" not in method and provider != "fedapay":
        return method_raw

    payment_channel = str(tx.get("payment_channel") or tx.get("channel") or "").strip().lower()
    card_brand = str(tx.get("card_brand") or tx.get("saved_card_type") or "").strip().lower()
    has_card_hint = payment_channel == "card" or bool(card_brand) or bool(tx.get("saved_card_id"))
    has_mobile_hint = payment_channel in {"mobile", "mobile_money"} or bool(tx.get("mobile_provider")) or "mobile" in method

    if has_card_hint:
        return "fedapay_card"
    if has_mobile_hint:
        return "mobile_money_fedapay"
    return "fedapay"


def _resolve_fedapay_fee_pct(policy: Dict[str, Any], country_code: Optional[str], mobile_provider: Optional[str] = None) -> float:
    provider_key = str(mobile_provider or "").strip().lower()
    is_card_hint = provider_key in {"card", "credit_card", "debit_card", "visa", "mastercard"} or any(
        token in provider_key for token in ("card", "visa", "master")
    )

    if is_card_hint:
        return _safe_float(resolve_card_fee_pct(policy, country_code), 0.0)

    mobile_fee = _safe_float(resolve_mobile_money_fee_pct(policy, country_code, mobile_provider), 0.0)
    if mobile_fee > 0:
        return mobile_fee

    return _safe_float(resolve_card_fee_pct(policy, country_code), 0.0)


def _payment_audit_tx_filter(tx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    tx = tx or {}
    if tx.get("transaction_id"):
        return {"transaction_id": tx.get("transaction_id")}
    if tx.get("payment_id"):
        return {"payment_id": tx.get("payment_id")}
    if tx.get("session_id"):
        return {"session_id": tx.get("session_id")}
    return {}


async def _update_payment_audit_state(tx: Optional[Dict[str, Any]], extra_set: Dict[str, Any]) -> None:
    tx_filter = _payment_audit_tx_filter(tx)
    if not tx_filter or not extra_set:
        return
    await db.payment_transactions.update_one(tx_filter, {"$set": extra_set})


async def _append_payment_audit_event(
    tx: Optional[Dict[str, Any]],
    *,
    event_type: str,
    title: str,
    detail: str,
    source: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    tx = tx or {}
    event = {
        "event_id": f"pae_{uuid.uuid4().hex[:12]}",
        "transaction_id": tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id"),
        "payment_id": tx.get("payment_id"),
        "session_id": tx.get("session_id"),
        "user_id": tx.get("user_id"),
        "provider": tx.get("provider") or tx.get("payment_method") or "payment",
        "event_type": event_type,
        "title": title,
        "detail": detail,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
    }
    await db.payment_audit_timeline_events.insert_one({**event})


async def _send_admin_payment_failure_alert(
    *,
    customer_email: str,
    plan_name: str,
    payment_method: str,
    reason: str,
    amount: float = 0.0,
    amount_local: float = 0.0,
    currency: str = "USD",
    reference_id: str = "",
):
    """Send admin alerts for failed/refunded payment events.

    Policy: failure alerts are in-app only by default; email is disabled unless explicitly enabled.
    """
    try:
        admin_targets = await _get_admin_receipt_recipients(exclude_email=customer_email)
        if not admin_targets:
            return

        method_label = _format_payment_method_label(payment_method)
        amount_display = (
            f"{amount_local:,.2f} {currency}"
            if currency and currency.upper() != "USD" and amount_local > 0
            else f"${amount:.2f}"
        )

        admin_users = await db.users.find(
            {"email": {"$in": admin_targets}},
            {"_id": 0, "user_id": 1},
        ).limit(50).to_list(50)

        for admin_user in admin_users:
            admin_user_id = admin_user.get("user_id")
            if not admin_user_id:
                continue
            await db.notifications.insert_one(
                {
                    "id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": admin_user_id,
                    "type": "admin_payment_failure_alert",
                    "title": "Admin Alert - Payment Failed",
                    "message": (
                        f"{plan_name} payment via {method_label} failed/refunded. "
                        f"Amount: {amount_display}. Reason: {reason}. Ref: {reference_id or 'N/A'}"
                    ),
                    "read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {
                        "customer_email": customer_email,
                        "plan": plan_name,
                        "payment_method": payment_method,
                        "reason": reason,
                        "amount": amount,
                        "amount_local": amount_local,
                        "currency": currency,
                        "reference_id": reference_id,
                    },
                }
            )

        if not ADMIN_FAILURE_ALERT_EMAIL_ENABLED:
            logger.info(
                "Admin payment failure email suppressed by policy: reference=%s method=%s reason=%s",
                reference_id,
                payment_method,
                reason,
            )
            return

        if is_email_configured():
            for admin_email in admin_targets:
                await send_catalog_template(
                    recipient_email=admin_email,
                    template_key="admin_payment_failure",
                    user_email=customer_email,
                    plan=plan_name,
                    amount=amount_display,
                    error=str(reason)[:200],
                    provider=payment_method or "Unknown",
                )
    except Exception as exc:
        logger.warning(f"Admin payment failure alert send failed: {exc}")


async def _send_user_payment_failure_recovery_email(
    *,
    user_id: str,
    user_email: str,
    user_name: str,
    plan_id: str,
    plan_name: str,
    billing_period: str,
    payment_method: str,
    amount_usd: float,
    currency: str,
    amount_local: float,
    session_id: str = "",
) -> Dict[str, Any]:
    """Send payment failure recovery email to user at most once per 24h."""
    if not is_email_configured():
        return {"sent": False, "reason": "email_not_configured"}
    if not user_email:
        return {"sent": False, "reason": "missing_user_email"}

    now = datetime.now(timezone.utc)
    daily_cutoff = (now - timedelta(hours=24)).isoformat()
    recent_recovery = await db.payment_recovery.find_one(
        {
            "user_id": user_id,
            "last_email_at": {"$gte": daily_cutoff},
            "status": "active",
            "recovered": False,
        },
        {"_id": 0, "token": 1, "last_email_at": 1},
        sort=[("last_email_at", -1)],
    )
    if recent_recovery:
        return {
            "sent": False,
            "reason": "daily_throttled",
            "token": recent_recovery.get("token"),
            "last_email_at": recent_recovery.get("last_email_at"),
        }

    amount_display = format_currency(
        amount_local if currency.upper() != "USD" and amount_local > 0 else amount_usd,
        currency,
    )
    token = await create_recovery_token(
        db,
        user_id,
        plan_id,
        billing_period,
        payment_method,
        amount_usd,
        currency=currency,
        amount_local=amount_local,
        session_id=session_id,
    )
    recovery_url = get_recovery_url(token)
    provider_result = await send_catalog_template(
        recipient_email=user_email,
        template_key="recovery_day1",
        user_name=user_name,
        plan_name=plan_name,
        amount=amount_display,
        recovery_link=recovery_url,
    )
    if provider_result.get("success"):
        await db.payment_recovery.update_one(
            {"token": token},
            {"$set": {"emails_sent": 1, "last_email_at": now.isoformat()}},
        )
        return {"sent": True, "token": token}

    return {
        "sent": False,
        "reason": "provider_send_failed",
        "token": token,
        "error": provider_result.get("error"),
    }


async def _send_payment_email(
    email: str,
    user_name: str,
    plan_name: str,
    amount: float,
    payment_method: str,
    ticket_id: str,
    billing_cycle: str,
    renewal_date: str,
    amount_local: float = 0,
    currency: str = "USD",
    gateway_fee: float = 0,
    transaction_context: Optional[Dict[str, Any]] = None,
    send_admin_alert: bool = True,
):
    """Send branded subscription confirmation + payment receipt with PDF attachment via email service."""
    result = {
        "email_configured": bool(is_email_configured()),
        "user_receipt_sent": False,
        "admin_receipt_sent": not send_admin_alert,
        "confirmation_email_sent": False,
        "admin_targets": [],
        "delivery_ok": False,
    }

    tx = transaction_context or {}
    normalized_money = _normalize_zero_decimal_checkout_amounts(
        tx,
        fallback_amount_usd=amount,
        fallback_currency=currency,
    )
    currency = str(normalized_money.get("currency") or currency or "USD").upper()
    amount_local = _safe_float(normalized_money.get("amount_local", amount_local), amount_local)
    if normalized_money.get("corrected"):
        tx = {
            **tx,
            "currency": currency,
            "subtotal": normalized_money.get("subtotal"),
            "tax_amount": normalized_money.get("tax_amount"),
            "processing_fee": normalized_money.get("processing_fee"),
            "amount_gross": normalized_money.get("amount_gross"),
            "amount_net": normalized_money.get("amount_net"),
            "total_amount": normalized_money.get("total_amount"),
            "amount_local": normalized_money.get("amount_local"),
            "fx_rate": normalized_money.get("fx_rate"),
            "pricing_autocorrected": True,
        }

    tx_currency_for_guard = str(tx.get("currency") or currency or "USD").upper()
    pricing_guard_amount = _safe_float(tx.get("amount", amount), amount)
    pricing_guard_currency = tx_currency_for_guard
    if tx_currency_for_guard != "USD" and tx.get("amount_usd") is not None:
        pricing_guard_amount = _safe_float(tx.get("amount_usd"), amount)
        pricing_guard_currency = "USD"

    pricing_candidate = {
        "plan_id": tx.get("plan_id") or (plan_name or "").lower(),
        "billing_period": tx.get("billing_period") or billing_cycle,
        "amount": pricing_guard_amount,
        "amount_gross": pricing_guard_amount,
        "total_amount": pricing_guard_amount,
        "payment_id": tx.get("payment_id") or tx.get("session_id") or ticket_id,
        "transaction_id": tx.get("transaction_id") or tx.get("payment_id") or ticket_id,
        "user_id": tx.get("user_id") or "",
        "currency": pricing_guard_currency,
    }
    try:
        plan_snapshot = await _assert_plan_pricing_or_block(pricing_candidate, context="payment_confirmation_email")
    except HTTPException as exc:
        result["pricing_mismatch_blocked"] = True
        result["pricing_mismatch_reason"] = str(exc.detail)
        result["delivery_ok"] = False
        return result

    plan_name = plan_snapshot["plan_name"]
    amount = plan_snapshot["expected_amount"]
    billing_cycle = plan_snapshot["billing_period"]
    tx = {
        **tx,
        "plan_id": plan_snapshot["plan_id"],
        "billing_period": billing_cycle,
    }
    tx_filter = _payment_audit_tx_filter(tx)
    if tx_filter:
        existing_delivery_state = await db.payment_transactions.find_one(
            tx_filter,
            {
                "_id": 0,
                "receipt_delivery_ok": 1,
                "user_receipt_sent": 1,
                "admin_receipt_sent": 1,
                "confirmation_email_sent": 1,
                "receipt_number": 1,
                "admin_targets": 1,
            },
        ) or {}
        if existing_delivery_state.get("receipt_delivery_ok"):
            return {
                "email_configured": bool(is_email_configured()),
                "user_receipt_sent": bool(existing_delivery_state.get("user_receipt_sent", True)),
                "admin_receipt_sent": bool(existing_delivery_state.get("admin_receipt_sent", True)),
                "confirmation_email_sent": bool(existing_delivery_state.get("confirmation_email_sent", True)),
                "admin_targets": existing_delivery_state.get("admin_targets") or [],
                "delivery_ok": True,
                "receipt_number": existing_delivery_state.get("receipt_number"),
                "skipped_duplicate_dispatch": True,
            }

    if not is_email_configured():
        logger.info(f"Email service not configured, skipping email to {email}")
        result["delivery_ok"] = True
        return result
    payment_date = datetime.now(timezone.utc).strftime("%b %d, %Y")
    target_lang = _detect_locale(transaction_context or {})

    try:
        from utils.receipt_generator import build_branded_receipt_html, generate_pdf_from_payment

        if ticket_id:
            receipt_seed = "".join(ch for ch in str(ticket_id).upper() if ch.isalnum())
        else:
            receipt_seed = "".join(
                ch for ch in str(tx.get("transaction_id") or tx.get("payment_id") or uuid.uuid4().hex).upper() if ch.isalnum()
            )
        receipt_suffix = (receipt_seed[-10:] or uuid.uuid4().hex[:10]).upper()
        receipt_number = f"RCT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{receipt_suffix}"

        tx = transaction_context or {}
        is_fr = _is_french_context(tx)
        subtotal = _safe_float(tx.get("subtotal", amount), amount)
        tax_amount = _safe_float(tx.get("tax_amount", 0), 0.0)
        processing_fee = _safe_float(tx.get("processing_fee", gateway_fee), gateway_fee)
        amount_gross = _safe_float(tx.get("amount_gross", subtotal + tax_amount), subtotal + tax_amount)
        total_amount = _safe_float(tx.get("total_amount", amount_gross), amount_gross)
        amount_net = _safe_float(tx.get("amount_net", max(total_amount - processing_fee, 0)), max(total_amount - processing_fee, 0))

        _receipt_payment = {
            "payment_id": tx.get("payment_id") or tx.get("session_id") or ticket_id or receipt_number,
            "transaction_id": tx.get("transaction_id") or tx.get("payment_id") or tx.get("session_id") or ticket_id,
            "plan_id": tx.get("plan_id") or (plan_name or "").lower(),
            "amount": amount,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "processing_fee": processing_fee,
            "amount_gross": amount_gross,
            "amount_net": amount_net,
            "total_amount": total_amount,
            "payment_method": _normalize_payment_method_for_display(tx.get("payment_method") or payment_method, tx),
            "provider": tx.get("provider") or tx.get("gateway") or payment_method,
            "status": tx.get("status") or tx.get("payment_status") or "completed",
            "created_at": tx.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "billing_period": tx.get("billing_period") or billing_cycle,
            "currency": tx.get("currency") or currency,
            "jurisdiction": tx.get("jurisdiction", {}),
            "product_type": _receipt_product_type_label(tx.get("product_type", "education_digital_service")),
            "tax_rate": _safe_float(tx.get("tax_rate", 0), 0.0),
            "tax_breakdown": tx.get("tax_breakdown", []),
            "locale": "fr" if is_fr else "en",
            "transparency_mode": bool(tx.get("transparency_mode", True)),
        }

        html_body = build_branded_receipt_html(
            receipt_number=receipt_number,
            user_name=user_name,
            user_email=email,
            plan_name=plan_name,
            amount_usd=amount,
            amount_local=amount_local,
            currency=currency,
            payment_method=_normalize_payment_method_for_display(payment_method, tx),
            billing_period=billing_cycle,
            payment_date=payment_date,
            renewal_date=renewal_date,
            gateway_fee=gateway_fee,
            ticket_id=ticket_id,
            payment_data=_receipt_payment,
        )
        pdf_bytes = generate_pdf_from_payment("receipt", _receipt_payment, user_name, email)

        import base64
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # Format amount for display
        currency_symbols = {"EUR": "\u20ac", "GBP": "\u00a3", "XOF": "CFA ", "XAF": "CFA ", "JPY": "\u00a5", "CAD": "CA$", "AUD": "A$", "INR": "\u20b9", "BRL": "R$", "NGN": "\u20a6", "KES": "KSh", "GHS": "GH\u20b5", "ZAR": "R"}
        cur = currency.upper()
        sym = currency_symbols.get(cur, f"{cur} ")
        if amount_local > 0 and cur != "USD":
            no_decimal = cur in ZERO_DECIMAL_CURRENCIES
            display_amount = f"{sym}{int(round(amount_local, 0)):,}" if no_decimal else f"{sym}{amount_local:,.2f}"
        else:
            display_amount = f"${total_amount:.2f}"

        method_label = _format_payment_method_label(
            _normalize_payment_method_for_display(payment_method, tx)
        )
        receipt_subject = f"Payment Receipt - {plan_name} Plan | {receipt_number}"
        receipt_text = f"Payment confirmed! Receipt {receipt_number} for {plan_name} plan - {display_amount}. See attached PDF."
        if str(tx.get("custom_receipt_subject") or "").strip():
            receipt_subject = str(tx.get("custom_receipt_subject")).strip()
        if str(tx.get("custom_receipt_text") or "").strip():
            receipt_text = str(tx.get("custom_receipt_text")).strip()
        if is_fr:
            receipt_subject = f"Reçu de paiement - Offre {plan_name} | {receipt_number}"
            receipt_text = f"Paiement confirmé ! Reçu {receipt_number} pour l'offre {plan_name} - {display_amount}. Voir le PDF en pièce jointe."
        elif target_lang not in {"", "en"}:
            try:
                from services.auto_translate import translate_batch

                translated_copy = await translate_batch([receipt_subject, receipt_text], target_lang)
                receipt_subject = translated_copy.get(receipt_subject, receipt_subject)
                receipt_text = translated_copy.get(receipt_text, receipt_text)
            except Exception as exc:
                logger.warning(f"Receipt copy localization fallback used ({target_lang}): {exc}")

        receipt_result = await send_email(
            recipient_email=email,
            subject=receipt_subject,
            content=html_body,
            recipient_name=user_name,
            contact_external_id=email,
            content_text=receipt_text,
            template_key="payment_receipt",
            attachments=[{
                "filename": build_pdf_v15_filename("receipt", receipt_number),
                "content": pdf_b64,
                "content_type": "application/pdf",
            }],
        )
        result["user_receipt_sent"] = bool(receipt_result.get("success"))
        if not receipt_result.get("success"):
            logger.error(f"Branded receipt email failed: {receipt_result.get('error')}")
        else:
            logger.info(f"Branded receipt email sent to {email}: {receipt_number}")
            result["user_receipt_sent_at"] = datetime.now(timezone.utc).isoformat()

        # Real-time admin receipt notification with the same receipt attachment
        admin_targets = await _get_admin_receipt_recipients(exclude_email=email) if send_admin_alert else []
        result["admin_targets"] = admin_targets
        if admin_targets:
            admin_subject = f"[Admin Alert] Payment Confirmed via {method_label} — {receipt_number}"
            if str(tx.get("custom_admin_receipt_subject") or "").strip():
                admin_subject = str(tx.get("custom_admin_receipt_subject")).strip()
            locked_admin_sent = _LOCKED_ADMIN_EMAIL not in admin_targets
            for admin_email in admin_targets:
                from utils.email_service import send_catalog_template
                admin_result = await send_catalog_template(
                    recipient_email=admin_email,
                    template_key="payment_admin_alert",
                    method=method_label,
                    amount=display_amount,
                    receipt_number=receipt_number,
                    user_email=email,
                    plan=plan_name,
                    attachments=[{
                        "filename": build_pdf_v15_filename("receipt", receipt_number),
                        "content": pdf_b64,
                        "content_type": "application/pdf",
                    }],
                )
                if admin_result.get("success"):
                    logger.info(f"Admin payment receipt email sent: {admin_email} ({receipt_number})")
                    result.setdefault("admin_receipt_events", []).append({
                        "email": admin_email,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    })
                    if admin_email == _LOCKED_ADMIN_EMAIL:
                        locked_admin_sent = True
                else:
                    logger.error(f"Admin payment receipt email failed for {admin_email}: {admin_result.get('error')}")
            result["admin_receipt_sent"] = locked_admin_sent
        else:
            result["admin_receipt_sent"] = not send_admin_alert
    except Exception as e:
        logger.error(f"Failed to send branded receipt to {email}: {e}")

    if LOCK_SINGLE_PAYMENT_COMMUNICATION:
        result["confirmation_email_sent"] = False
    else:
        try:
            is_fr = _is_french_context(transaction_context or {})
            if is_fr:
                confirmation_subject = f"Abonnement {plan_name} activé — RealAICoach"
                confirmation_html = f"""
                <div style='font-family:Arial,sans-serif;line-height:1.6;color:#0F172A;padding:24px;'>
                  <h2 class='em-title' style='margin:0 0 10px;color:#0F172A;'>Votre abonnement est actif</h2>
                  <p class='em-text' style='color:#374151;'>Bonjour {user_name or 'Utilisateur'},</p>
                  <p class='em-text' style='color:#374151;'>Votre abonnement <strong class='em-strong' style='color:#0F172A;'>{plan_name}</strong> ({billing_cycle}) est maintenant actif.</p>
                  <p class='em-text' style='color:#374151;'>Prochain renouvellement : <strong class='em-strong' style='color:#0F172A;'>{renewal_date}</strong>.</p>
                  <p class='em-text' style='color:#374151;'>Un reçu détaillé a été envoyé avec les informations fiscales et les frais de traitement.</p>
                  <p class='em-text-secondary' style='margin-top:14px;color:#64748B;font-size:12px;'>Merci d'utiliser RealAICoach.</p>
                </div>
                """
                confirmation_text = (
                    f"Bonjour {user_name or 'Utilisateur'}, votre abonnement {plan_name} ({billing_cycle}) est actif. "
                    f"Renouvellement: {renewal_date}. Un reçu détaillé a été envoyé."
                )
            else:
                if _is_subscription_restoration(tx):
                    confirmation_template = build_subscription_restored_email(
                        user_name=user_name,
                        plan_name=plan_name,
                        renewal_date=renewal_date,
                    )
                    if not str(tx.get("custom_confirmation_text") or "").strip():
                        tx["custom_confirmation_text"] = (
                            f"Welcome back, {user_name or 'there'}. Your {plan_name} subscription is active again. "
                            f"Next renewal: {renewal_date}. Open your dashboard to continue."
                        )
                else:
                    confirmation_template = build_subscription_confirmation_email(
                        user_name=user_name,
                        plan_name=plan_name,
                        billing_cycle=billing_cycle,
                        renewal_date=renewal_date,
                    )
                confirmation_subject = confirmation_template.subject
                confirmation_html = confirmation_template.html
                confirmation_text = confirmation_template.text
                if target_lang not in {"", "en"}:
                    try:
                        from services.auto_translate import translate_batch, translate_email_html

                        translated_subject, translated_html = await translate_email_html(confirmation_html, confirmation_subject, target_lang)
                        translated_text_map = await translate_batch([confirmation_text], target_lang)
                        confirmation_subject = translated_subject
                        confirmation_html = translated_html
                        confirmation_text = translated_text_map.get(confirmation_text, confirmation_text)
                    except Exception as exc:
                        logger.warning(f"Confirmation email localization fallback used ({target_lang}): {exc}")
            if str(tx.get("custom_confirmation_subject") or "").strip():
                confirmation_subject = str(tx.get("custom_confirmation_subject")).strip()
            if str(tx.get("custom_confirmation_text") or "").strip():
                confirmation_text = str(tx.get("custom_confirmation_text")).strip()
            confirmation_email_type = "subscription_restored" if _is_subscription_restoration(tx) else "subscription_confirmed"
            confirmation_result = await send_email(
                recipient_email=email,
                subject=confirmation_subject,
                content=confirmation_html,
                recipient_name=user_name,
                contact_external_id=email,
                content_text=confirmation_text,
                template_key=confirmation_email_type,
            )
            result["confirmation_email_sent"] = bool(confirmation_result.get("success"))
            result["confirmation_email_type"] = confirmation_email_type
            result["confirmation_subject"] = confirmation_subject
            try:
                from utils.email_notifications import _log_email

                await _log_email(
                    tx.get("user_id") or "unknown",
                    email,
                    confirmation_email_type,
                    confirmation_subject,
                    "sent" if confirmation_result.get("success") else "failed",
                    message_id=confirmation_result.get("message_id", ""),
                    error=confirmation_result.get("error", "") if not confirmation_result.get("success") else "",
                )
            except Exception:
                pass
            if not confirmation_result.get("success"):
                logger.error(f"Subscription confirmation email failed: {confirmation_result.get('error')}")
        except Exception as e:
            logger.error(f"Failed to send subscription confirmation to {email}: {e}")

    result["delivery_ok"] = (
        not result["email_configured"]
        or (
            result["user_receipt_sent"]
            and result["admin_receipt_sent"]
        )
    )
    result["receipt_number"] = locals().get("receipt_number")

    audit_state = {
        "receipt_number": result.get("receipt_number"),
        "ticket_id": ticket_id,
        "user_receipt_sent": result.get("user_receipt_sent", False),
        "admin_receipt_sent": result.get("admin_receipt_sent", False),
        "confirmation_email_sent": result.get("confirmation_email_sent", False),
        "receipt_delivery_ok": result.get("delivery_ok", False),
        "admin_targets": result.get("admin_targets", []),
    }
    if result.get("user_receipt_sent_at"):
        audit_state["user_receipt_sent_at"] = result.get("user_receipt_sent_at")
    if result.get("admin_receipt_events"):
        audit_state["admin_receipt_events"] = result.get("admin_receipt_events")
        audit_state["admin_receipt_sent_at"] = result.get("admin_receipt_events", [{}])[-1].get("sent_at")
    await _update_payment_audit_state(tx, audit_state)

    if result.get("user_receipt_sent"):
        await _append_payment_audit_event(
            tx,
            event_type="user_receipt_email_sent",
            title="User receipt email sent",
            detail=f"Receipt {result.get('receipt_number')} delivered to {email}.",
            source="payment_email",
            metadata={"receipt_number": result.get("receipt_number"), "ticket_id": ticket_id},
        )
    if result.get("admin_receipt_events"):
        for item in result.get("admin_receipt_events", []):
            await _append_payment_audit_event(
                tx,
                event_type="admin_receipt_email_sent",
                title="Admin receipt email sent",
                detail=f"Receipt {result.get('receipt_number')} delivered to {item.get('email')}",
                source="payment_email",
                metadata={"receipt_number": result.get("receipt_number"), "admin_email": item.get("email")},
            )
    if result.get("confirmation_email_sent"):
        await _append_payment_audit_event(
            tx,
            event_type="subscription_confirmation_sent",
            title="Subscription confirmation email sent",
            detail=f"Confirmation email delivered to {email}",
            source="payment_email",
            metadata={"ticket_id": ticket_id},
        )
    return result


# ── Payment confirmation notification (in-app + email) ──
async def _send_payment_notification(
    user_id: str,
    email: str,
    user_name: str,
    plan_name: str,
    amount: float,
    payment_method: str,
    ticket_id: str,
    billing_cycle: str,
    renewal_date: str,
    currency: str = "USD",
    amount_local: float = 0,
    transaction_context: Optional[Dict[str, Any]] = None,
):
    """Create in-app notification + send email for payment confirmation."""
    tx_ctx = transaction_context or {}
    tx_filter = _payment_audit_tx_filter(tx_ctx)
    tx_dispatch_ref = (
        tx_ctx.get("transaction_id")
        or tx_ctx.get("payment_id")
        or tx_ctx.get("session_id")
        or ""
    )

    normalized_money = _normalize_zero_decimal_checkout_amounts(
        tx_ctx,
        fallback_amount_usd=amount,
        fallback_currency=currency,
    )
    currency = str(normalized_money.get("currency") or currency or "USD").upper()
    amount_local = _safe_float(normalized_money.get("amount_local", amount_local), amount_local)

    if normalized_money.get("corrected"):
        tx_ctx = {
            **tx_ctx,
            "currency": currency,
            "subtotal": normalized_money.get("subtotal"),
            "tax_amount": normalized_money.get("tax_amount"),
            "processing_fee": normalized_money.get("processing_fee"),
            "amount_gross": normalized_money.get("amount_gross"),
            "amount_net": normalized_money.get("amount_net"),
            "total_amount": normalized_money.get("total_amount"),
            "amount_local": normalized_money.get("amount_local"),
            "fx_rate": normalized_money.get("fx_rate"),
            "fx_base_currency": tx_ctx.get("fx_base_currency") or "USD",
            "pricing_autocorrected": True,
        }
        if tx_filter:
            await db.payment_transactions.update_one(
                tx_filter,
                {
                    "$set": {
                        "currency": currency,
                        "subtotal": normalized_money.get("subtotal"),
                        "tax_amount": normalized_money.get("tax_amount"),
                        "processing_fee": normalized_money.get("processing_fee"),
                        "amount_gross": normalized_money.get("amount_gross"),
                        "amount_net": normalized_money.get("amount_net"),
                        "total_amount": normalized_money.get("total_amount"),
                        "amount_local": normalized_money.get("amount_local"),
                        "fx_rate": normalized_money.get("fx_rate"),
                        "fx_base_currency": tx_ctx.get("fx_base_currency") or "USD",
                        "pricing_autocorrected": True,
                        "pricing_autocorrected_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        logger.warning(
            "Auto-corrected zero-decimal pricing scale for tx=%s currency=%s",
            tx_dispatch_ref or tx_filter,
            currency,
        )

    if _should_suppress_payment_notifications(tx_ctx):
        if tx_filter:
            await db.payment_transactions.update_one(
                tx_filter,
                {
                    "$set": {
                        "notification_sent": True,
                        "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                        "notification_suppressed": True,
                        "notification_suppression_reason": str(
                            tx_ctx.get("notification_suppression_reason") or "synthetic_internal_transaction"
                        ),
                        "notification_dispatch_lock_until": 0,
                    }
                },
            )
        logger.info(
            "Skipping payment notification dispatch for suppressed tx=%s",
            tx_dispatch_ref or tx_filter,
        )
        return {
            "skipped": True,
            "reason": "suppressed_synthetic_transaction",
            "transaction_ref": tx_dispatch_ref,
        }

    # Idempotency lock: one payment transaction should trigger only one notification/email dispatch.
    # Lock auto-expires to prevent permanent stalls if any downstream provider fails.
    if tx_filter:
        now_ts = int(time.time())
        lock_doc = await db.payment_transactions.find_one_and_update(
            {
                **tx_filter,
                "notification_sent": {"$ne": True},
                "$or": [
                    {"notification_dispatch_lock_until": {"$exists": False}},
                    {"notification_dispatch_lock_until": {"$lt": now_ts}},
                ],
            },
            {
                "$set": {
                    "notification_dispatch_lock_until": now_ts + 3600,
                    "notification_dispatch_started_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not lock_doc:
            logger.info(
                f"Skipping duplicate payment notification dispatch for tx={tx_dispatch_ref or tx_filter}"
            )
            return {
                "skipped": True,
                "reason": "already_sent_or_in_progress",
                "transaction_ref": tx_dispatch_ref,
            }

    resolved_lang = _detect_locale(tx_ctx)
    is_fr = resolved_lang == "fr"
    charged_amount = _safe_float(tx_ctx.get("total_amount", amount_local if currency != "USD" else amount), amount)
    # Format amount display based on currency
    if currency != "USD" and amount_local > 0:
        currency_symbols = {"EUR": "\u20ac", "GBP": "\u00a3", "XOF": "CFA ", "XAF": "CFA ", "JPY": "\u00a5", "CAD": "CA$", "AUD": "A$", "INR": "\u20b9", "BRL": "R$", "NGN": "\u20a6", "KES": "KSh", "GHS": "GH\u20b5", "ZAR": "R"}
        sym = currency_symbols.get(currency, f"{currency} ")
        no_decimal = currency in ("JPY", "KRW", "XOF", "XAF")
        amount_str = f"{sym}{int(amount_local):,}" if no_decimal else f"{sym}{amount_local:,.2f}"
    else:
        amount_str = f"${charged_amount:.2f}"

    display_payment_method = _normalize_payment_method_for_display(payment_method, tx_ctx)
    method_label = _format_payment_method_label(display_payment_method)
    custom_notif_title = str(tx_ctx.get("custom_notification_title") or "").strip()
    custom_notif_message = str(tx_ctx.get("custom_notification_message") or "").strip()

    if custom_notif_title:
        notif_title = custom_notif_title
        notif_message = custom_notif_message or (
            f"Your payment of {amount_str} via {method_label} has been processed. You're now subscribed to the {plan_name} plan. eTicket: {ticket_id}"
        )
    elif is_fr:
        notif_title = f"Paiement confirmé - Offre {plan_name}"
        notif_message = (
            f"Votre paiement de {amount_str} via {method_label} a été traité avec succès. "
            f"Votre abonnement {plan_name} est maintenant actif. Reçu: {ticket_id}"
        )
    else:
        notif_title = f"Payment Confirmed - {plan_name} Plan"
        notif_message = (
            f"Your payment of {amount_str} via {method_label} has been processed. "
            f"You're now subscribed to the {plan_name} plan. eTicket: {ticket_id}"
        )
        if resolved_lang not in {"", "en"}:
            try:
                from services.auto_translate import translate_batch

                translated = await translate_batch([notif_title, notif_message], resolved_lang)
                notif_title = translated.get(notif_title, notif_title)
                notif_message = translated.get(notif_message, notif_message)
            except Exception as exc:
                logger.warning(f"In-app payment notification localization fallback used ({resolved_lang}): {exc}")

    notif_id = f"notif_{uuid.uuid4().hex[:12]}"
    notif = {
        "id": notif_id,
        "notification_id": notif_id,
        "user_id": user_id,
        "type": "payment_confirmation",
        "title": notif_title,
        "message": notif_message,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "plan": plan_name,
                "amount": charged_amount,
            "ticket_id": ticket_id,
            "payment_method": payment_method,
            "currency": currency,
            "amount_local": amount_local,
            "transaction_id": (transaction_context or {}).get("transaction_id"),
            "transaction_ref": tx_dispatch_ref,
            "tax_amount": (transaction_context or {}).get("tax_amount"),
            "amount_gross": (transaction_context or {}).get("amount_gross"),
            "amount_net": (transaction_context or {}).get("amount_net"),
                "locale": resolved_lang or ("fr" if is_fr else "en"),
        },
    }
    await db.notifications.insert_one({**notif})
    await _push_realtime_notification(user_id, notif)
    logger.info(f"In-app payment notification sent to user {user_id}")
    await _append_payment_audit_event(
        tx_ctx,
        event_type="user_in_app_notification_created",
        title="User in-app notification created",
        detail=f"Notification {notif_id} created for {user_id}",
        source="notifications",
        metadata={"notification_id": notif_id, "ticket_id": ticket_id},
    )

    # Create admin in-app alert regardless of email provider availability
    admin_notif_ids = await _create_admin_payment_alert_notification(
        customer_email=email,
        customer_name=user_name,
        plan_name=plan_name,
        payment_method=payment_method,
        ticket_id=ticket_id,
        billing_cycle=billing_cycle,
        amount=charged_amount,
        amount_local=amount_local,
        currency=currency,
        transaction_context=tx_ctx,
    )
    if admin_notif_ids:
        for admin_notif_id in admin_notif_ids:
            await _append_payment_audit_event(
                tx_ctx,
                event_type="admin_in_app_alert_created",
                title="Admin in-app alert created",
                detail=f"Admin alert {admin_notif_id} created for payment confirmation",
                source="notifications",
                metadata={"notification_id": admin_notif_id, "ticket_id": ticket_id},
            )
    await _update_payment_audit_state(
        tx_ctx,
        {
            "ticket_id": ticket_id,
            "user_notification_id": notif_id,
            "admin_notification_ids": admin_notif_ids or [],
        },
    )

    email_result = await _send_payment_email(
        email,
        user_name or "User",
        plan_name,
        amount,
        payment_method,
        ticket_id,
        billing_cycle,
        renewal_date,
        amount_local=amount_local,
        currency=currency,
        transaction_context=tx_ctx,
    ) or {
        "email_configured": bool(is_email_configured()),
        "delivery_ok": not is_email_configured(),
        "user_receipt_sent": False,
        "admin_receipt_sent": False,
    }

    if email_result.get("email_configured") and not email_result.get("delivery_ok"):
        raise RuntimeError(
            "payment_email_delivery_incomplete: "
            f"user_receipt_sent={email_result.get('user_receipt_sent')} "
            f"admin_receipt_sent={email_result.get('admin_receipt_sent')}"
        )

    if tx_filter:
        await db.payment_transactions.update_one(
            tx_filter,
            {
                "$set": {
                    "notification_sent": True,
                    "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                    "notification_dispatch_lock_until": 0,
                    "notification_dispatch_ref": tx_dispatch_ref,
                    "notification_dispatch_ticket_id": ticket_id,
                },
                "$inc": {"notification_dispatch_count": 1},
            },
        )

    return {
        "notification_id": notif_id,
        "admin_notification_ids": admin_notif_ids or [],
        "email_result": email_result,
    }


# Missed-notification recovery route lives in payments_recovery_routes.py.


# ── Endpoints ──


@router.get("/subscriptions/plans")
async def get_subscription_plans(request: Request, response: Response):
    currency = request.query_params.get("currency", "USD").upper()
    if currency not in SUPPORTED_CURRENCIES:
        currency = "USD"

    cur_info = SUPPORTED_CURRENCIES[currency]
    fx_rate = cur_info["rate"]
    symbol = cur_info["symbol"]
    is_zero_decimal = currency in ZERO_DECIMAL_CURRENCIES

    plans_out = []
    gps_plans = await get_subscription_plans_from_gps()
    for plan in gps_plans.values():
        p = dict(plan)
        if currency != "USD" and p["monthly_price"] > 0:
            m = p["monthly_price"] * fx_rate
            y = p["yearly_price"] * fx_rate
            p["monthly_price"] = round(m) if is_zero_decimal else round(m, 2)
            p["yearly_price"] = round(y) if is_zero_decimal else round(y, 2)
        p["currency"] = currency
        p["currency_symbol"] = symbol
        plans_out.append(p)

    response.headers["X-Endpoint-Scope"] = "public-user"
    response.headers["X-Admin-Endpoint-Equivalent"] = "/api/admin/subscriptions/plans"
    return {
        "plans": plans_out,
        "currency": currency,
        "currency_symbol": symbol,
        "fx_rate": fx_rate,
    }


@router.post("/subscriptions/pricing-guard/frontend-event")
async def pricing_guard_frontend_event(req: Request):
    user = await _get_user_from_request(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = await req.json()
    except Exception:
        payload = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    event_type = str(payload.get("event_type") or "unknown")[:80]
    event_doc = {
        "event_type": event_type,
        "plan_id": str(payload.get("plan_id") or "")[:80],
        "billing_period": str(payload.get("billing_period") or "")[:30],
        "route": str(payload.get("route") or "")[:220],
        "payment_method": str(payload.get("payment_method") or "")[:40],
        "currency": str(payload.get("currency") or "")[:12],
        "param_price": payload.get("param_price"),
        "canonical_price": payload.get("canonical_price"),
        "reason": str(payload.get("reason") or "")[:500],
        "user_id": str(getattr(user, "user_id", "") or "")[:120],
        "user_email": str(getattr(user, "email", "") or "")[:320],
        "created_at": now_iso,
    }

    await db.subscription_pricing_guard_events.insert_one(event_doc)
    if event_type in {"source_unavailable_blocked", "param_mismatch_autocorrected"}:
        await db.subscription_pricing_guard_incidents.insert_one(
            {
                **event_doc,
                "severity": "high" if event_type == "source_unavailable_blocked" else "medium",
            }
        )

    return {"ok": True, "created_at": now_iso}


@router.post("/subscriptions/checkout/frontend-event")
async def checkout_frontend_event(req: Request):
    user = await _get_user_from_request(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = await req.json()
    except Exception:
        payload = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    event_doc = {
        "event_type": str(payload.get("event_type") or "unknown")[:80],
        "route": str(payload.get("route") or "")[:220],
        "plan_id": str(payload.get("plan_id") or "")[:80],
        "billing_period": str(payload.get("billing_period") or "")[:30],
        "payment_method": normalize_payment_method(payload.get("payment_method")),
        "currency": str(payload.get("currency") or "")[:12],
        "reason": str(payload.get("reason") or "")[:500],
        "error_message": str(payload.get("error_message") or "")[:500],
        "user_id": str(getattr(user, "user_id", "") or "")[:120],
        "user_email": str(getattr(user, "email", "") or "")[:320],
        "created_at": now_iso,
    }
    await db.subscription_checkout_frontend_events.insert_one(event_doc)
    return {"ok": True, "created_at": now_iso}


def _normalize_trust_provider(method: str) -> str:
    raw = str(method or "").strip().lower()
    if raw in {"card", "stripe"}:
        return "stripe"
    if raw in {"paypal"}:
        return "paypal"
    if raw in {"fedapay", "mobile_money", "mobile"}:
        return "fedapay"
    if raw in {"all"}:
        return "all"
    return "unknown"


@router.get("/admin/subscriptions/trust-funnel-analytics")
async def trust_funnel_analytics(request: Request, minutes: int = 10080):
    await require_admin(request)
    window_minutes = max(60, min(int(minutes or 10080), 60 * 24 * 60))
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()

    metrics: Dict[str, Dict[str, Any]] = {}
    event_filter = {
        "event_type": {"$in": ["trust_explainer_open", "trust_checkout_conversion_click"]},
        "created_at": {"$gte": cutoff},
    }
    async for row in iter_find_paginated(
        db.subscription_pricing_guard_events,
        event_filter,
        {"_id": 0, "event_type": 1, "payment_method": 1},
    ):
        provider = _normalize_trust_provider(str(row.get("payment_method") or ""))
        if provider not in metrics:
            metrics[provider] = {"provider": provider, "open_count": 0, "conversion_click_count": 0}
        if row.get("event_type") == "trust_explainer_open":
            metrics[provider]["open_count"] += 1
        elif row.get("event_type") == "trust_checkout_conversion_click":
            metrics[provider]["conversion_click_count"] += 1

    ordered = ["stripe", "paypal", "fedapay", "all", "unknown"]
    providers = []
    for key in ordered:
        bucket = metrics.get(key)
        if not bucket:
            continue
        opens = int(bucket.get("open_count") or 0)
        conversions = int(bucket.get("conversion_click_count") or 0)
        bucket["conversion_rate_pct"] = round((conversions / opens) * 100, 2) if opens > 0 else 0.0
        providers.append(bucket)

    total_opens = sum(item["open_count"] for item in providers)
    total_conversions = sum(item["conversion_click_count"] for item in providers)

    return {
        "window_minutes": window_minutes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers,
        "totals": {
            "open_count": total_opens,
            "conversion_click_count": total_conversions,
            "conversion_rate_pct": round((total_conversions / total_opens) * 100, 2) if total_opens > 0 else 0.0,
        },
    }


@router.get("/subscriptions/user-plan-info")
async def get_user_plan_info(req: Request):
    user = await _get_user_from_request(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "access_locked": 1, "subscription_permanent": 1, "full_access": 1, "is_admin": 1},
    )
    access_locked = user_doc.get("access_locked", False) if user_doc else False
    subscription_permanent = user_doc.get("subscription_permanent", False) if user_doc else False
    plan_id = getattr(user, "subscription_plan", "free") or "free"
    plan = await get_subscription_plan_from_gps(plan_id, default_plan_id="free")
    is_privileged = bool(getattr(user, "is_admin", False))
    if is_privileged:
        plan = await get_subscription_plan_from_gps("premium", default_plan_id="free")
        plan_id = "premium"
    if not plan:
        raise HTTPException(status_code=503, detail="Subscription plans unavailable")
    return {
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "badge": plan.get("badge", plan_id),
        "features": plan.get("features", []),
        "limitations": plan.get("limitations", []),
        "export_formats": plan.get("export_formats", []),
        "automation_enabled": plan.get("automation_enabled", False),
        "print_enabled": plan.get("print_enabled", False),
        "history_days": plan.get("history_days", 7),
        "daily_conversation_limit": plan.get("daily_conversation_limit", 3),
        "is_privileged": is_privileged,
        "access_locked": access_locked,
        "subscription_permanent": subscription_permanent,
    }


@router.post("/subscriptions/checkout-preview")
async def checkout_preview(payload: CheckoutPreviewRequest, req: Request):
    """Transparent pre-checkout amounts so users can review Tax Fee + Processing Fee before payment."""
    user = await _get_user_from_request(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    preview = await _compute_checkout_breakdown(user, req, payload)
    preview.pop("internal", None)
    return preview


@router.get("/admin/payments/checkout-kill-switch")
async def admin_get_checkout_kill_switch(request: Request):
    await require_admin(request)
    return await get_checkout_kill_switch_state(db)


@router.put("/admin/payments/checkout-kill-switch")
async def admin_set_checkout_kill_switch(request: Request):
    admin = await require_admin(request)
    payload = await request.json() if request.method else {}

    enabled = bool((payload or {}).get("enabled", False))
    reason = str((payload or {}).get("reason") or DEFAULT_CHECKOUT_PAUSE_MESSAGE).strip()
    saved = await set_checkout_kill_switch_state(
        db,
        enabled=enabled,
        reason=reason,
        updated_by=str(getattr(admin, "user_id", "admin")),
        source="admin_settings",
    )

    if enabled:
        try:
            from routes.admin_push_notifications import emit_realtime_alert

            await emit_realtime_alert(
                alert_type="checkout_kill_switch_enabled",
                severity="critical",
                title="Checkout Global Kill-Switch Enabled",
                message=reason,
            )
        except Exception as exc:
            logger.warning(f"checkout kill-switch realtime alert failed: {exc}")

    return {"status": "saved", "state": saved}


@router.post("/subscriptions/create-checkout")
async def create_checkout(request: CreateCheckoutRequest, req: Request):
    user = await _get_user_from_request(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await raise_if_checkout_paused(db)

    orchestration_request_id = (
        str(req.headers.get("X-Request-ID") or "").strip()
        or f"orch_{uuid.uuid4().hex[:12]}"
    )

    normalized_method = normalize_payment_method(request.payment_method)
    request.payment_method = normalized_method
    if normalized_method not in CANONICAL_PAYMENT_METHODS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid payment method. Use one of: "
                "stripe, paypal, fedapay, apple_iap, google_iap."
            ),
        )

    # Check if user is access-locked + existing active plan state
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

    plan = await require_paid_subscription_plan(request.plan_id)

    saved_card = await _resolve_saved_card_for_checkout(user.user_id, request.saved_card_id)
    saved_card_meta = _build_saved_card_metadata(saved_card)

    amount = plan["monthly_price"] if request.billing_period == "monthly" else plan["yearly_price"]
    product_type = resolve_product_type(request.plan_id, request.product_type)
    jurisdiction = _resolve_jurisdiction(
        req,
        country_code=request.country_code,
        state_code=request.state_code,
        postal_code=request.postal_code,
        user=user,
    )
    base_url = _resolve_checkout_frontend_base(req)

    # ── Stripe checkout (for card payments) ──
    if request.payment_method == "stripe" and STRIPE_API_KEY:
        stripe_result = await _create_stripe_checkout_response(
            checkout_request=request,
            http_request=req,
            user=user,
            plan=plan,
            saved_card=saved_card,
            saved_card_meta=saved_card_meta,
            amount=amount,
            product_type=product_type,
            jurisdiction=jurisdiction,
            base_url=base_url,
        )
        if isinstance(stripe_result, dict):
            stripe_session = str(stripe_result.get("session_id") or "")
            if stripe_session:
                await _append_checkout_transition(
                    {"session_id": stripe_session, "user_id": user.user_id},
                    state="handoff_ready",
                    source="subscriptions:create-checkout",
                    detail="Stripe checkout URL generated",
                    meta={"request_id": orchestration_request_id, "provider": "stripe"},
                )
            stripe_result["orchestration_request_id"] = orchestration_request_id
        return stripe_result

    # ── PayPal checkout ──
    elif request.payment_method == "paypal":
        try:
            return_url = f"{base_url}/subscription/success"
            cancel_url = f"{base_url}/subscription/plans?status=cancelled&gateway=paypal"

            preview = await _compute_checkout_breakdown(
                user,
                req,
                CheckoutPreviewRequest(
                    plan_id=request.plan_id,
                    billing_period=request.billing_period,
                    payment_method="paypal",
                    currency="USD",
                    country_code=request.country_code,
                    state_code=request.state_code,
                    postal_code=request.postal_code,
                    product_type=request.product_type,
                    preferred_language=request.preferred_language,
                    browser_language=request.browser_language,
                    browser_languages=request.browser_languages,
                ),
                enforce_methods=("stripe", "paypal", "fedapay"),
            )
            internal = preview.get("internal", {})
            financials = internal.get("financials", {})
            tax_quote = internal.get("tax_quote", {})
            localization_context = preview.get("localization_context", {})
            transaction_id = f"txn_{uuid.uuid4().hex[:16]}"

            order = await _create_paypal_order(
                amount=financials["total_amount"],
                currency=preview.get("currency", "USD"),
                plan_name=plan["name"],
                user_id=user.user_id,
                plan_id=request.plan_id,
                billing_period=request.billing_period,
                return_url=return_url,
                cancel_url=cancel_url,
                subtotal=financials["subtotal"],
                tax_amount=financials["tax_amount"],
                product_type=product_type,
                country_code=jurisdiction.get("country", "US"),
                state_code=jurisdiction.get("state", ""),
            )

            approve_url = None
            for link in order.get("links", []):
                if link.get("rel") in ("approve", "payer-action"):
                    approve_url = link.get("href")
                    break
            if not approve_url and order.get("id"):
                paypal_base = "https://www.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://www.paypal.com"
                approve_url = f"{paypal_base}/checkoutnow?token={order['id']}"

            await db.payment_transactions.insert_one(
                {
                    "transaction_id": transaction_id,
                    "session_id": order.get("id", ""),
                    "user_id": user.user_id,
                    "plan_id": request.plan_id,
                    "billing_period": request.billing_period,
                    "amount": amount,
                    "amount_local": financials["total_amount"],
                    "currency": str(preview.get("currency", "USD")).lower(),
                    "original_usd_amount": amount,
                    "fx_rate": preview.get("fx_rate", _fx_rate_for(preview.get("currency", "USD"), 1.0)),
                    "fx_base_currency": preview.get("fx_base_currency", "USD"),
                    "provider": "paypal",
                    "payment_method": "paypal",
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
                        _build_checkout_transition(
                            "created",
                            "subscriptions:create-checkout",
                            "PayPal checkout transaction created",
                            {"request_id": orchestration_request_id, "provider": "paypal"},
                        ),
                        _build_checkout_transition(
                            "handoff_ready",
                            "subscriptions:create-checkout",
                            "PayPal checkout URL generated",
                            {"request_id": orchestration_request_id, "provider": "paypal"},
                        ),
                    ],
                    "orchestration_request_id": orchestration_request_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            await log_tax_calculation(
                db,
                transaction_id=transaction_id,
                provider="paypal",
                user_id=user.user_id,
                payload={"phase": "checkout_create", "tax_quote": tax_quote, "financials": financials},
            )
            await append_financial_ledger_entry(
                db,
                event_type="checkout_initiated",
                transaction_id=transaction_id,
                provider="paypal",
                user_id=user.user_id,
                payload={
                    "status": "initiated",
                    "payment_session": order.get("id", ""),
                    "financials": financials,
                    "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
                    "product_type": product_type,
                    "saved_card": saved_card,
                },
            )

            return {
                "order_id": order.get("id"),
                "checkout_url": approve_url,
                "paypal_client_id": PAYPAL_CLIENT_ID,
                "amount": amount,
                "plan_id": request.plan_id,
                "billing_period": request.billing_period,
                "payment_method": "paypal",
                "orchestration_request_id": orchestration_request_id,
                "saved_card": saved_card,
                "checkout_breakdown": {k: v for k, v in preview.items() if k != "internal"},
            }
        except Exception as e:
            logger.error(f"PayPal order creation error: {e}")
            raise HTTPException(status_code=500, detail="Failed to create PayPal order")

    # ── FedaPay / Mobile Money checkout orchestration ──
    elif request.payment_method == "fedapay":
        fedapay_currency = str(request.currency or "XOF").upper()
        if fedapay_currency not in {"XOF", "XAF"}:
            fedapay_currency = "XOF"

        if not request.phone_number:
            return {
                "payment_method": "fedapay",
                "provider": "fedapay",
                "action_type": "route",
                "checkout_url": f"{base_url}/subscription/mobile-money",
                "route": "/subscription/mobile-money",
                "message": "Phone number is required for FedaPay mobile-money checkout.",
                "required_fields": ["phone_number", "mobile_provider"],
                "currency": fedapay_currency,
                "checkout_state_hint": "route_required",
                "orchestration_request_id": orchestration_request_id,
            }

        mobile_payload = _fedapay_routes.MobileMoneySubscriptionRequest(
            plan_id=request.plan_id,
            billing_period=request.billing_period,
            gateway="fedapay",
            phone_number=request.phone_number,
            currency=fedapay_currency,
            saved_card_id=request.saved_card_id,
            mobile_provider=request.mobile_provider,
        )
        fedapay_result = await _fedapay_routes.mobile_money_subscription(mobile_payload, req)
        fedapay_payment_id = str(fedapay_result.get("payment_id") or "")
        fedapay_ticket_id = str(fedapay_result.get("ticket_id") or "")
        if fedapay_payment_id or fedapay_ticket_id:
            tx_filter: Dict[str, Any] = {"user_id": user.user_id}
            if fedapay_payment_id and fedapay_ticket_id:
                tx_filter["$or"] = [{"payment_id": fedapay_payment_id}, {"session_id": fedapay_ticket_id}]
            elif fedapay_payment_id:
                tx_filter["payment_id"] = fedapay_payment_id
            else:
                tx_filter["session_id"] = fedapay_ticket_id
            await _append_checkout_transition(
                tx_filter,
                state="handoff_ready" if fedapay_result.get("payment_url") else "initiated",
                source="subscriptions:create-checkout",
                detail="FedaPay checkout initiated",
                meta={"request_id": orchestration_request_id, "provider": "fedapay"},
            )
        return {
            **fedapay_result,
            "provider": "fedapay",
            "action_type": "redirect_url" if fedapay_result.get("payment_url") else "none",
            "checkout_url": fedapay_result.get("payment_url", ""),
            "orchestration_request_id": orchestration_request_id,
        }

    # ── Apple/Google IAP handoff orchestration ──
    elif request.payment_method in {"apple_iap", "google_iap"}:
        from routes.iap import _resolve_iap_provider_readiness

        readiness = _resolve_iap_provider_readiness()
        provider_key = "apple" if request.payment_method == "apple_iap" else "google"
        provider_row = (readiness.get("providers") or {}).get(provider_key) or {}
        if not bool(provider_row.get("configured") or provider_row.get("sandbox_probe_configured")):
            raise HTTPException(
                status_code=503,
                detail=f"{request.payment_method} is not configured in this environment.",
            )

        return {
            "payment_method": request.payment_method,
            "provider": request.payment_method,
            "action_type": "route",
            "route": "/subscription/mobile",
            "checkout_url": f"{base_url}/subscription/mobile?planId={request.plan_id}&billingPeriod={request.billing_period}&provider={provider_key}",
            "iap_readiness": provider_row,
            "message": "Continue in mobile store checkout flow.",
            "checkout_state_hint": "route_handoff",
            "orchestration_request_id": orchestration_request_id,
        }

    raise HTTPException(
        status_code=400,
        detail="Invalid payment method. Use one of: stripe, paypal, fedapay, apple_iap, google_iap.",
    )


@router.post("/subscriptions/initiate-checkout")
async def initiate_checkout(request: CreateCheckoutRequest, req: Request):
    """Unified payment orchestration endpoint for all subscription providers."""
    result = await create_checkout(request, req)
    if isinstance(result, dict):
        return {
            "orchestration_version": "v2",
            "provider": str(result.get("provider") or request.payment_method),
            "payment_method": str(result.get("payment_method") or request.payment_method),
            "action_type": str(result.get("action_type") or ("redirect_url" if result.get("checkout_url") else "none")),
            **result,
        }
    return result


# ── PayPal JS SDK and webhook routes live in payments_paypal_routes.py ──


# ── FedaPay/mobile-money routes live in payments_fedapay_routes.py ──


@router.post("/payments/confirm")
async def confirm_payment(request: Request):
    body_raw = await request.json()
    body = ConfirmPaymentRequest(**body_raw)
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    lookup_id = body.session_id or body.payment_id
    if not lookup_id:
        raise HTTPException(status_code=400, detail="session_id or payment_id is required")

    tx = await db.payment_transactions.find_one(
        {
            "user_id": user.user_id,
            "$or": [{"session_id": lookup_id}, {"payment_id": lookup_id}],
        },
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="No matching payment transaction found")

    tx_session_id = tx.get("session_id")
    tx_payment_id = tx.get("payment_id") or tx_session_id or lookup_id
    tx_plan_id = tx.get("plan_id") or body.plan_id
    tx_billing_period = tx.get("billing_period") or body.billing_period or "monthly"
    tx_method = tx.get("payment_method") or body.payment_method or "stripe"
    tx_status = str(tx.get("payment_status") or "").lower()

    plan = await get_subscription_plan_from_gps(tx_plan_id)
    if not plan or plan.get("id") == "free":
        raise HTTPException(status_code=400, detail="Invalid paid plan on transaction")

    completed_statuses = {"paid", "completed", "succeeded"}
    # For Stripe, re-check provider status if transaction is not yet marked completed.
    if tx_status not in completed_statuses and tx_method == "stripe" and tx_session_id and STRIPE_API_KEY:
        try:
            stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
            stripe_status = await stripe_checkout.get_checkout_status(tx_session_id)
            if str(stripe_status.payment_status or "").lower() == "paid":
                tx_status = "paid"
                await db.payment_transactions.update_one(
                    {"session_id": tx_session_id},
                    {
                        "$set": {
                            "payment_status": "completed",
                            "provider_confirmed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
        except Exception as e:
            logger.warning(f"Stripe status verification failed for {tx_session_id}: {e}")

    if tx_status not in completed_statuses:
        await _append_checkout_transition(
            {"user_id": user.user_id, "$or": [{"session_id": tx_session_id}, {"payment_id": tx_payment_id}]},
            state="awaiting_provider_confirmation",
            source="payments:confirm",
            detail="Payment confirmation attempted before provider completion",
            meta={"payment_method": tx_method},
        )
        raise HTTPException(status_code=402, detail="Payment not completed yet. Please complete checkout first.")

    existing_payment = await db.payments.find_one(
        {"user_id": user.user_id, "payment_id": tx_payment_id},
        {"_id": 0, "payment_id": 1},
    )

    if tx_method == "stripe" and tx_session_id:
        stripe_financials = await _fetch_stripe_session_financials(tx_session_id)
        if stripe_financials:
            merged_financials = _merge_stripe_provider_financials(tx, stripe_financials)
            await db.payment_transactions.update_one(
                {"session_id": tx_session_id},
                {
                    "$set": {
                        "provider": "stripe",
                        **merged_financials,
                    }
                },
            )
            tx = {**tx, **merged_financials, "provider": "stripe", "currency": merged_financials.get("currency", tx.get("currency", "usd"))}

    tx = {**tx, "transaction_id": tx.get("transaction_id") or tx_payment_id, "payment_id": tx_payment_id, "payment_method": tx_method}

    end_date = datetime.now(timezone.utc) + timedelta(days=365 if tx_billing_period == "yearly" else 30)
    amount = _safe_float(tx.get("amount_gross", 0), plan["monthly_price"] if tx_billing_period == "monthly" else plan["yearly_price"])
    lifecycle_context = await _get_subscription_lifecycle_state(user.user_id)

    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "subscription_plan": tx_plan_id,
                "subscription_status": "active",
                "subscription_end_date": end_date,
                "payment_verified": True,
                "last_payment_id": tx_payment_id,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    tx = {**tx, **lifecycle_context}

    await _append_checkout_transition(
        {"user_id": user.user_id, "$or": [{"session_id": tx_session_id}, {"payment_id": tx_payment_id}]},
        state="activated",
        source="payments:confirm",
        detail="Subscription activated after confirmed provider payment",
        meta={"payment_method": tx_method, "plan_id": tx_plan_id},
    )

    if not existing_payment:
        await db.payments.insert_one(_build_payment_record_from_tx(tx, status="completed"))

    await append_financial_ledger_entry(
        db,
        event_type="payment_confirmed",
        transaction_id=tx.get("transaction_id"),
        provider=tx_method,
        user_id=user.user_id,
        payload={
            "session_id": tx_session_id,
            "payment_id": tx_payment_id,
            "amount_gross": tx.get("amount_gross"),
            "tax_amount": tx.get("tax_amount"),
            "processing_fee": tx.get("processing_fee"),
            "amount_net": tx.get("amount_net"),
        },
    )

    ticket_id = f"SUB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    await db.subscription_audit_log.insert_one(
        {
            "user_id": user.user_id,
            "action": "payment_confirmed_verified",
            "plan_id": tx_plan_id,
            "amount": amount,
            "payment_method": tx_method,
            "session_id": tx_session_id,
            "timestamp": datetime.now(timezone.utc),
        }
    )

    should_notify = not tx.get("notification_sent")
    if should_notify:
        renewal_date = end_date.strftime("%b %d, %Y")
        try:
            await _send_payment_notification(
                user.user_id,
                user.email,
                getattr(user, "name", ""),
                plan["name"],
                amount,
                tx_method,
                ticket_id,
                tx_billing_period,
                renewal_date,
                currency=tx.get("currency", "USD").upper(),
                amount_local=tx.get("total_amount", tx.get("amount_gross", amount)),
                transaction_context=tx,
            )
            await db.payment_transactions.update_one(
                {"session_id": tx_session_id} if tx_session_id else {"payment_id": tx_payment_id},
                {"$set": {"notification_sent": True, "notification_sent_at": datetime.now(timezone.utc).isoformat(), "payment_status": "completed"}},
            )
        except Exception as exc:
            logger.error(f"Payment confirmation notification dispatch failed for {tx_session_id or tx_payment_id}: {exc}")
            await _queue_payment_notification_recovery(tx, str(exc))

    return {
        "success": True,
        "ticket_id": ticket_id,
        "subscription_plan": tx_plan_id,
        "subscription_end_date": end_date.isoformat(),
        "message": f"Successfully subscribed to {plan['name']} plan!",
        "confirmation": f"Subscription confirmed! Your eTicket: {ticket_id}",
    }


@router.post("/subscriptions/confirm-payment")
async def confirm_payment_alias(request: Request):
    """Backward-compatible alias used by older clients."""
    return await confirm_payment(request)


@router.post("/subscriptions/paypal/capture")
async def capture_paypal_payment(request: Request):
    body = await request.json()
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    order_id = body.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="Order ID required")

    try:
        capture_result = await _capture_paypal_order(order_id)

        if capture_result.get("status") == "COMPLETED":
            purchase_unit = capture_result.get("purchase_units", [{}])[0]
            custom_id = purchase_unit.get("payments", {}).get("captures", [{}])[0].get("custom_id", "")

            parts = custom_id.split("|")
            plan_id = parts[1] if len(parts) >= 3 else body.get("plan_id", "basic")
            billing_period = parts[2] if len(parts) >= 3 else body.get("billing_period", "monthly")

            plan = await get_subscription_plan_from_gps(plan_id)
            if not plan:
                raise HTTPException(status_code=400, detail="Invalid plan")

            end_date = datetime.now(timezone.utc) + timedelta(days=365 if billing_period == "yearly" else 30)
            amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]

            await db.users.update_one(
                {"user_id": user.user_id},
                {
                    "$set": {
                        "subscription_plan": plan_id,
                        "subscription_status": "active",
                        "subscription_end_date": end_date,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

            capture_obj = purchase_unit.get("payments", {}).get("captures", [{}])[0] or {}
            capture_id = capture_obj.get("id", order_id)
            tx_existing = await db.payment_transactions.find_one({"session_id": order_id}, {"_id": 0}) or {}

            amount_block = purchase_unit.get("amount", {}) if isinstance(purchase_unit, dict) else {}
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
            lifecycle_context = await _get_subscription_lifecycle_state(user.user_id)

            tx_update = {
                "payment_status": "completed",
                "provider": "paypal",
                "payment_method": "paypal",
                "fee_pass_through": True,
                "payment_id": capture_id,
                "paypal_capture_id": capture_id,
                "provider_capture_payload": capture_obj,
                "status": "completed",
                "subtotal": financials["subtotal"],
                "tax_amount": financials["tax_amount"],
                "processing_fee": financials["processing_fee"],
                "amount_gross": financials["amount_gross"],
                "amount_net": financials["amount_net"],
                "total_amount": financials["total_amount"],
                **lifecycle_context,
            }
            await db.payment_transactions.update_one(
                {"session_id": order_id},
                {"$set": tx_update},
            )

            tx_final = {
                **tx_existing,
                **tx_update,
                "session_id": order_id,
                "user_id": user.user_id,
                "plan_id": plan_id,
                "billing_period": billing_period,
                "transaction_id": tx_existing.get("transaction_id") or order_id,
            }

            existing_payment = await db.payments.find_one({"payment_id": capture_id}, {"_id": 0, "payment_id": 1})
            if not existing_payment:
                await db.payments.insert_one(_build_payment_record_from_tx(tx_final, status="completed"))

            ticket_id = f"PAY-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
            renewal_date = end_date.strftime("%b %d, %Y")
            # Fetch currency/transaction data for exact receipt details
            pp_tx = await db.payment_transactions.find_one({"session_id": order_id}, {"_id": 0})
            pp_currency = (pp_tx.get("currency", "usd") if pp_tx else "usd").upper()
            pp_amount_local = pp_tx.get("total_amount", pp_tx.get("amount_local", 0)) if pp_tx else 0
            notification_recovery_queued = False
            try:
                await _send_payment_notification(
                    user.user_id,
                    user.email,
                    getattr(user, "name", ""),
                    plan["name"],
                    pp_tx.get("amount_gross", amount) if pp_tx else amount,
                    "paypal",
                    ticket_id,
                    billing_period,
                    renewal_date,
                    currency=pp_currency,
                    amount_local=pp_amount_local,
                    transaction_context=pp_tx,
                )
                await _mark_payment_notification_sent({"session_id": order_id})
            except Exception as exc:
                notification_recovery_queued = True
                logger.error(f"PayPal capture notification dispatch failed for {order_id}: {exc}")
                await _queue_payment_notification_recovery(pp_tx or tx_final, str(exc))

            return {
                "success": True,
                "ticket_id": ticket_id,
                "subscription_plan": plan_id,
                "subscription_end_date": end_date.isoformat(),
                "message": f"Successfully subscribed to {plan['name']} plan!",
                "capture_id": capture_id,
                "notification_recovery_queued": notification_recovery_queued,
            }
        else:
            raise HTTPException(status_code=400, detail=f"Payment not completed: {capture_result.get('status')}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PayPal capture error: {e}")
        raise HTTPException(status_code=500, detail="Failed to capture payment")


@router.post("/subscriptions/cancel")
async def cancel_subscription(request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if getattr(user, "subscription_plan", "free") == "free":
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    reason = body.get("reason", "no_reason_given")
    feedback = body.get("feedback", "")

    ticket_id = f"CXL-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    boundary = getattr(user, "subscription_end_date", None)
    if not boundary:
        boundary = datetime.now(timezone.utc)
    if isinstance(boundary, str):
        try:
            boundary = datetime.fromisoformat(boundary.replace("Z", "+00:00"))
        except Exception:
            boundary = datetime.now(timezone.utc)
    if getattr(boundary, "tzinfo", None) is None:
        boundary = boundary.replace(tzinfo=timezone.utc)

    await db.users.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "subscription_status": "cancelled",
                "pending_subscription_transition": {
                    "action": "cancel",
                    "target_plan": "free",
                    "requested_at": now_iso,
                    "effective_at": boundary.isoformat(),
                    "requested_by": user.user_id,
                    "reason": reason,
                },
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    await db.support_tickets.insert_one(
        {
            "ticket_id": ticket_id,
            "type": "cancellation",
            "user_id": user.user_id,
            "email": user.email,
            "plan_cancelled": user.subscription_plan,
            "reason": reason,
            "feedback": feedback,
            "status": "processed",
            "created_at": now_iso,
        }
    )

    # In-app notification
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user.user_id,
            notif_type="subscription_cancelled",
            title="Subscription Cancelled",
            body=f"Your {user.subscription_plan} plan has been cancelled. Access continues until end of billing period. Ref: {ticket_id}",
            action_url="/subscription/plans",
        )
    except Exception:
        await db.notifications.insert_one(
            {
                "id": f"notif_{uuid.uuid4().hex[:12]}",
                "user_id": user.user_id,
                "type": "subscription_cancelled",
                "title": "Subscription Cancelled",
                "message": f"Your {user.subscription_plan} subscription has been cancelled. Access continues until the end of your billing period. eTicket: {ticket_id}",
                "read": False,
                "created_at": now_iso,
            }
        )

    # Notify admins
    try:
        from routes.notification_engine import emit_notification

        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(10)
        for admin in admins:
            await emit_notification(
                user_id=admin["user_id"],
                notif_type="subscription_cancelled_admin",
                title=f"Cancellation: {user.email}",
                body=f"Plan: {user.subscription_plan}. Reason: {reason}. Ref: {ticket_id}",
                action_url="/admin-console",
            )
    except Exception:
        pass

    if is_email_configured():
        try:
            end_date = getattr(user, "subscription_end_date", None) or "end of billing period"
            result = await send_catalog_template(
                recipient_email=user.email,
                template_key="subscription_cancelled",
                recipient_name=user.name or user.email,
                user_name=user.name or user.email,
                plan_name=user.subscription_plan,
                end_date=str(end_date),
            )
            if not result.get("success"):
                logger.error(f"Subscription cancellation email failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Subscription cancellation email error: {e}")

    # Broadcast real-time subscription update via WebSocket
    try:
        from utils.ws_manager import broadcast_data_change
        await broadcast_data_change("subscription", "cancelled", user.user_id)
    except Exception:
        pass

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": "Your subscription has been cancelled. You will have access until the end of your billing period.",
        "confirmation": f"Cancellation confirmed. Your eTicket: {ticket_id}",
        "subscription_plan": user.subscription_plan,
        "subscription_end_date": getattr(user, "subscription_end_date", None),
    }


@router.get("/subscriptions/status")
async def get_subscription_status(request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from utils.access_control_engine import compute_effective_plan, reconcile_due_transition

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "user_id": 1,
            "is_admin": 1,
            "full_access": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "subscription_permanent": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
        },
    ) or {
        "user_id": user.user_id,
        "is_admin": getattr(user, "is_admin", False),
        "full_access": getattr(user, "full_access", False),
        "subscription_plan": getattr(user, "subscription_plan", "free"),
        "subscription_status": getattr(user, "subscription_status", "active"),
        "subscription_end_date": getattr(user, "subscription_end_date", None),
        "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
        "payment_verified": getattr(user, "payment_verified", False),
    }
    user_doc, _ = await reconcile_due_transition(db, user_doc)

    is_privileged = bool(user_doc.get("is_admin", False))
    effective_plan = "premium" if is_privileged else compute_effective_plan(user_doc)

    plan = await get_subscription_plan_from_gps(effective_plan, default_plan_id="free")
    if not plan:
        raise HTTPException(status_code=503, detail="Subscription plans unavailable")
    end_date_raw = user_doc.get("subscription_end_date")
    end_date_str = None
    if end_date_raw:
        end_date_str = end_date_raw.isoformat() if hasattr(end_date_raw, "isoformat") else str(end_date_raw)

    # Build feature access map for the user's tier
    from routes.feature_access import FEATURE_ACCESS
    features = {}
    for feature_name, tiers in FEATURE_ACCESS.items():
        features[feature_name] = tiers.get(effective_plan, tiers.get("free"))

    # Daily AI usage
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    progress = await db.progress.find_one({"user_id": user.user_id}, {"_id": 0})
    daily_used = 0
    if progress and progress.get("last_conversation_date") == today:
        daily_used = progress.get("daily_conversations", 0)

    return {
        "subscription_plan": effective_plan,
        "subscription_status": user_doc.get("subscription_status", "active"),
        "subscription_end_date": end_date_str,
        "pending_subscription_transition": user_doc.get("pending_subscription_transition"),
        "plan_name": plan["name"],
        "is_privileged": is_privileged,
        "features": features,
        "plan_features": plan.get("features", []),
        "plan_limitations": plan.get("limitations", []),
        "daily_conversation_limit": plan.get("daily_conversation_limit", 3),
        "daily_conversations_used": daily_used,
        "export_formats": plan.get("export_formats", []),
        "automation_enabled": plan.get("automation_enabled", False),
        "print_enabled": plan.get("print_enabled", False),
        "history_days": plan.get("history_days", 7),
        "payment_verified": user_doc.get("payment_verified", False) if not is_privileged else True,
    }


@router.post("/subscriptions/reactivate")
async def reactivate_subscription(request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    current_status = getattr(user, "subscription_status", "active")
    if current_status != "cancelled":
        raise HTTPException(status_code=400, detail="Subscription is not cancelled")

    await db.users.update_one({"user_id": user.user_id}, {"$set": {"subscription_status": "active"}})
    await db.users.update_one({"user_id": user.user_id}, {"$unset": {"pending_subscription_transition": ""}})

    return {
        "success": True,
        "message": "Subscription reactivated successfully",
        "subscription_plan": user.subscription_plan,
        "subscription_status": "active",
    }


@router.get("/subscriptions/my-subscription")
async def get_my_subscription(request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    plan = await get_subscription_plan_from_gps(getattr(user, "subscription_plan", "free"), default_plan_id="free")
    if not plan:
        raise HTTPException(status_code=503, detail="Subscription plans unavailable")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    progress = await db.progress.find_one({"user_id": user.user_id}, {"_id": 0})
    daily_used = 0
    if progress and progress.get("last_conversation_date") == today:
        daily_used = progress.get("daily_conversations", 0)

    end_date_raw = getattr(user, "subscription_end_date", None)
    end_date = end_date_raw.isoformat() if hasattr(end_date_raw, "isoformat") else str(end_date_raw) if end_date_raw else None

    return {
        "plan": plan,
        "status": getattr(user, "subscription_status", "active"),
        "end_date": end_date,
        "daily_conversations_used": daily_used,
        "daily_conversation_limit": plan.get("daily_conversation_limit", 3),
    }


@router.get("/subscriptions/renewal-banner")
async def get_renewal_banner(request: Request):
    """Get renewal banner data for in-app display. Shows if subscription is expiring soon or expired."""
    user = await _get_user_from_request(request)
    if not user:
        return {"show_banner": False}

    plan = getattr(user, "subscription_plan", "free")
    getattr(user, "subscription_status", "active")
    end_date = getattr(user, "subscription_end_date", None)

    # Free users: show upgrade prompt
    if plan == "free":
        return {
            "show_banner": True,
            "banner_type": "upgrade",
            "title": "Upgrade Your Plan",
            "message": f"Unlock unlimited features with {get_plan_name('basic')} ({get_monthly_price_label('basic')}) or {get_plan_name('premium')} ({get_monthly_price_label('premium')}).",
            "cta_text": "View Plans",
            "cta_url": "/subscription/plans",
            "urgency": "low",
        }

    # Paid users: check expiry
    if end_date:
        if isinstance(end_date, str):
            try:
                end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                return {"show_banner": False}
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days_left = (end_date - now).days

        if days_left < 0:
            return {
                "show_banner": True,
                "banner_type": "expired",
                "title": "Subscription Expired",
                "message": f"Your {plan.capitalize()} plan has expired. Renew now to restore access.",
                "cta_text": "Renew Now",
                "cta_url": "/subscription/plans",
                "urgency": "critical",
                "days_left": 0,
            }
        elif days_left <= 1:
            return {
                "show_banner": True,
                "banner_type": "expiring",
                "title": "Expiring Today!",
                "message": f"Your {plan.capitalize()} plan expires today. Renew to avoid losing access.",
                "cta_text": "Renew Now",
                "cta_url": "/subscription/plans",
                "urgency": "critical",
                "days_left": days_left,
            }
        elif days_left <= 3:
            return {
                "show_banner": True,
                "banner_type": "expiring",
                "title": f"Expiring in {days_left} days",
                "message": f"Your {plan.capitalize()} plan expires on {end_date.strftime('%b %d')}. Renew to continue uninterrupted.",
                "cta_text": "Renew Now",
                "cta_url": "/subscription/plans",
                "urgency": "high",
                "days_left": days_left,
            }
        elif days_left <= 7:
            return {
                "show_banner": True,
                "banner_type": "reminder",
                "title": f"Renew in {days_left} days",
                "message": f"Your {plan.capitalize()} plan renews on {end_date.strftime('%b %d, %Y')}.",
                "cta_text": "Manage Subscription",
                "cta_url": "/subscription/plans",
                "urgency": "medium",
                "days_left": days_left,
            }

    # Check for recent failed payments (last 7 days only)
    # But ONLY show the banner if the subscription is NOT currently active/valid
    # This prevents false positives from test transactions
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    sub_is_active = (
        plan not in ["free", None, ""]
        and getattr(user, "subscription_status", "") == "active"
        and end_date is not None
        and (isinstance(end_date, datetime) and end_date > datetime.now(timezone.utc))
    )
    if not sub_is_active:
        failed_tx = await db.payment_transactions.find_one(
            {
                "user_id": user.user_id,
                "payment_status": {"$in": ["failed", "retry_pending"]},
                "created_at": {"$gte": seven_days_ago},
            },
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if failed_tx:
            return {
                "show_banner": True,
                "banner_type": "payment_failed",
                "title": "Payment Failed",
                "message": "Your last payment didn't go through. Update your payment method to keep your subscription active.",
                "cta_text": "Update Payment",
                "cta_url": "/subscription/plans",
                "urgency": "high",
            }

    return {"show_banner": False}


@router.post("/subscriptions/retry-payment")
async def retry_payment(request: Request):
    """Retry a failed payment for the user's current subscription."""
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Find the latest failed transaction
    failed_tx = await db.payment_transactions.find_one(
        {"user_id": user.user_id, "payment_status": {"$in": ["failed", "retry_pending", "expired"]}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not failed_tx:
        raise HTTPException(status_code=400, detail="No failed payment to retry")

    retry_count = failed_tx.get("retry_count", 0) + 1
    if retry_count > 3:
        raise HTTPException(status_code=400, detail="Maximum retry attempts reached. Please create a new subscription.")

    # Redirect to create a new checkout for the same plan
    plan_id = failed_tx.get("plan_id", "basic")
    billing_period = failed_tx.get("billing_period", "monthly")

    await db.payment_transactions.update_one(
        {"session_id": failed_tx["session_id"]},
        {"$set": {"retry_count": retry_count, "last_retry_at": datetime.now(timezone.utc).isoformat()}},
    )

    await db.subscription_audit_log.insert_one(
        {
            "user_id": user.user_id,
            "action": "manual_payment_retry",
            "plan_id": plan_id,
            "retry_count": retry_count,
            "timestamp": datetime.now(timezone.utc),
        }
    )

    return {
        "message": "Payment retry initiated",
        "plan_id": plan_id,
        "billing_period": billing_period,
        "retry_count": retry_count,
        "action": "redirect_to_checkout",
        "checkout_url": "/subscription/plans",
    }


# Payment history, receipts, invoices, and tax-statement routes live in payments_history_routes.py.


# ============== PAYMENT CARDS MANAGEMENT ==============
# Card route handlers live in payments_cards_routes.py and are registered above.


# ── Admin subscription routes live in payments_subscription_admin.py ──


# User-facing payment analytics route lives in payments_user_analytics_routes.py.

# Admin renewal reminder routes live in payments_admin_maintenance_routes.py.


# ─── Payment reporting/export routes live in payments_reporting_routes.py ───


# Executive billing pack route lives in payments_admin_maintenance_routes.py.


# ─── Ad-blocker-proof proxy endpoints with generic names live in payments_document_proxy_routes.py ───


# Ad-blocker-safe document proxy routes live in payments_document_proxy_routes.py.


# ─── Receipt Branding Customization ───────────────────────────────────


# Admin payment-history export settings and receipt branding routes live in payments_admin_maintenance_routes.py.


# ════════════════════════════════════════════════════════════
# PAYMENT FAILURE RECOVERY ENDPOINTS# ════════════════════════════════════════════════════════════
# PAYMENT FAILURE RECOVERY ENDPOINTS
# ════════════════════════════════════════════════════════════


# Stripe checkout-status and webhook routes live in payments_stripe_routes.py.

@router.get("/subscriptions/recover/{token}")
async def recover_subscription(token: str):
    """Validate a recovery token and redirect to pre-filled checkout."""
    token_doc = await validate_recovery_token(db, token)
    if not token_doc:
        return JSONResponse(
            status_code=400,
            content={"error": "This recovery link has expired or is no longer valid."},
        )
    plan_id = token_doc.get("plan_id", "basic")
    period = token_doc.get("billing_period", "monthly")
    method = token_doc.get("payment_method", "stripe")
    currency = token_doc.get("currency", "usd").lower()
    redirect_url = f"/subscription/plans?recover={token}&plan={plan_id}&period={period}&method={method}&currency={currency}"
    base = os.environ.get("FRONTEND_BASE_URL", "")
    return RedirectResponse(url=f"{base}{redirect_url}")


@router.post("/subscriptions/recover/{token}/checkout")
async def recover_subscription_checkout(token: str, request: Request):
    """Create a checkout session from a recovery token."""
    token_doc = await validate_recovery_token(db, token)
    if not token_doc:
        return JSONResponse(
            status_code=400,
            content={"error": "This recovery link has expired or is no longer valid."},
        )
    user_id = token_doc["user_id"]
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
    if not user:
        return JSONResponse(status_code=404, content={"error": "User not found."})

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    plan_id = body.get("plan_id", token_doc.get("plan_id", "basic"))
    billing_period = body.get("billing_period", token_doc.get("billing_period", "monthly"))
    payment_method = body.get("payment_method", token_doc.get("payment_method", "stripe"))
    currency = body.get("currency", token_doc.get("currency", "usd")).lower()

    # Create the checkout via the existing flow
    # Simulate the checkout creation
    plan = await get_subscription_plan_from_gps(plan_id)
    if not plan:
        return JSONResponse(status_code=400, content={"error": "Invalid plan."})

    amount = plan["monthly_price"] if billing_period == "monthly" else plan["yearly_price"]
    if amount == 0:
        return JSONResponse(status_code=400, content={"error": "Cannot checkout for a free plan."})

    # Mark token as recovered
    await mark_recovered(db, token, new_session_id="pending")

    # Return the data needed for the frontend to create a regular checkout
    return JSONResponse(content={
        "plan_id": plan_id,
        "billing_period": billing_period,
        "payment_method": payment_method,
        "currency": currency,
        "amount": amount,
        "plan_name": plan["name"],
        "token_validated": True,
    })


# Payment recovery stats and tax-compliance audit routes live in payments_admin_maintenance_routes.py.
