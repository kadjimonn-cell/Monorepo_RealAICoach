"""Shared checkout models and helper functions for payments routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from utils.payment_localization import detect_payment_locale, resolve_payment_localization_context
from utils.tax_compliance_engine import build_financial_totals, calculate_tax_quote, estimate_processing_fee, resolve_product_type
from utils.fedapay_policy_service import get_fedapay_policy, resolve_checkout_fee_visibility_policy

from .db import db
from .payments_catalog import require_paid_subscription_plan
from .payments_fedapay_routes import MOBILE_MONEY_FX, _resolve_fedapay_fee_pct


# ── Supported currencies with display metadata ──
SUPPORTED_CURRENCIES = {
    "USD": {"symbol": "$", "name": "US Dollar", "rate": 1.0, "stripe_supported": True},
    "EUR": {"symbol": "\u20ac", "name": "Euro", "rate": 0.92, "stripe_supported": True},
    "GBP": {"symbol": "\u00a3", "name": "British Pound", "rate": 0.79, "stripe_supported": True},
    "CAD": {"symbol": "CA$", "name": "Canadian Dollar", "rate": 1.36, "stripe_supported": True},
    "AUD": {"symbol": "A$", "name": "Australian Dollar", "rate": 1.53, "stripe_supported": True},
    "JPY": {"symbol": "\u00a5", "name": "Japanese Yen", "rate": 149.5, "stripe_supported": True},
    "CNY": {"symbol": "\u00a5", "name": "Chinese Yuan", "rate": 7.24, "stripe_supported": False},
    "INR": {"symbol": "\u20b9", "name": "Indian Rupee", "rate": 83.1, "stripe_supported": True},
    "BRL": {"symbol": "R$", "name": "Brazilian Real", "rate": 4.97, "stripe_supported": True},
    "KRW": {"symbol": "\u20a9", "name": "South Korean Won", "rate": 1320.0, "stripe_supported": True},
    "MXN": {"symbol": "MX$", "name": "Mexican Peso", "rate": 17.15, "stripe_supported": True},
    "NGN": {"symbol": "\u20a6", "name": "Nigerian Naira", "rate": 1580.0, "stripe_supported": True},
    "XOF": {"symbol": "CFA", "name": "CFA Franc (BCEAO)", "rate": 605.0, "stripe_supported": False},
    "XAF": {"symbol": "FCFA", "name": "CFA Franc (BEAC)", "rate": 605.0, "stripe_supported": False},
    "GHS": {"symbol": "GH\u20b5", "name": "Ghanaian Cedi", "rate": 14.5, "stripe_supported": False},
    "ZAR": {"symbol": "R", "name": "South African Rand", "rate": 18.7, "stripe_supported": True},
    "AED": {"symbol": "AED", "name": "UAE Dirham", "rate": 3.67, "stripe_supported": True},
    "SAR": {"symbol": "SAR", "name": "Saudi Riyal", "rate": 3.75, "stripe_supported": True},
    "TRY": {"symbol": "\u20ba", "name": "Turkish Lira", "rate": 30.5, "stripe_supported": True},
    "RUB": {"symbol": "\u20bd", "name": "Russian Ruble", "rate": 92.0, "stripe_supported": False},
    "THB": {"symbol": "\u0e3f", "name": "Thai Baht", "rate": 35.5, "stripe_supported": True},
    "PLN": {"symbol": "z\u0142", "name": "Polish Zloty", "rate": 4.02, "stripe_supported": True},
    "SEK": {"symbol": "kr", "name": "Swedish Krona", "rate": 10.45, "stripe_supported": True},
}

# Zero-decimal currencies (amount in smallest unit = 1 unit, not 100 cents)
ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "XOF", "XAF"}
PAYPAL_SUPPORTED_CURRENCIES = {
    "AUD", "BRL", "CAD", "CNY", "EUR", "GBP", "JPY", "MXN", "NZD", "PLN", "SEK", "CHF", "THB", "USD",
}

# Last FX update timestamp
_fx_last_updated: str = ""



# ── Canonical Pydantic schemas ──
# Moved to `/app/backend/models/payments.py` (Phase 2 model migration).
# Re-imported here so the public API surface (routes that `from
# .payments_checkout_core import CreateCheckoutRequest`) keeps working.
from models.payments import (  # noqa: E402
    CheckoutPreviewRequest,
)


CANONICAL_PAYMENT_METHODS = {"stripe", "paypal", "fedapay", "apple_iap", "google_iap"}
PAYMENT_METHOD_ALIASES = {
    "card": "stripe",
    "stripe": "stripe",
    "paypal": "paypal",
    "feda": "fedapay",
    "fedapay": "fedapay",
    "mobile_money": "fedapay",
    "mobile-money": "fedapay",
    "apple": "apple_iap",
    "apple_iap": "apple_iap",
    "ios_iap": "apple_iap",
    "google": "google_iap",
    "google_iap": "google_iap",
    "play_iap": "google_iap",
}


def normalize_payment_method(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return PAYMENT_METHOD_ALIASES.get(raw, raw)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _resolve_jurisdiction(
    req: Optional[Request] = None,
    *,
    country_code: Optional[str] = None,
    state_code: Optional[str] = None,
    postal_code: Optional[str] = None,
    user: Any = None,
) -> Dict[str, str]:
    headers = req.headers if req else {}
    user_country = getattr(user, "country", "") if user else ""
    user_state = getattr(user, "state", "") if user else ""
    user_postal = getattr(user, "postal_code", "") if user else ""
    country = (
        country_code
        or headers.get("x-country-code")
        or headers.get("cf-ipcountry")
        or headers.get("x-vercel-ip-country")
        or user_country
        or "US"
    )
    state = state_code or headers.get("x-state-code") or headers.get("x-vercel-ip-country-region") or user_state or ""
    postal = postal_code or headers.get("x-postal-code") or user_postal or ""
    return {
        "country": str(country or "US").strip().upper(),
        "state": str(state or "").strip().upper(),
        "postal_code": str(postal or "").strip(),
    }


def _extract_tx_financials(tx: Dict[str, Any], *, fee_pass_through_default: bool = False) -> Dict[str, float]:
    amount = _safe_float(tx.get("amount", tx.get("amount_usd", 0)), 0.0)
    normalized = _normalize_zero_decimal_checkout_amounts(tx, fallback_amount_usd=amount, fallback_currency=str(tx.get("currency", "USD")))
    subtotal = _safe_float(normalized.get("subtotal", tx.get("subtotal", amount)), amount)
    tax_amount = _safe_float(normalized.get("tax_amount", tx.get("tax_amount", 0)), 0.0)
    processing_fee = _safe_float(
        normalized.get("processing_fee", tx.get("processing_fee", tx.get("fee", tx.get("fee_local", 0)))),
        0.0,
    )
    fee_pass_through = bool(tx.get("fee_pass_through", fee_pass_through_default))
    return build_financial_totals(
        subtotal=subtotal,
        tax_amount=tax_amount,
        processing_fee=processing_fee,
        fee_pass_through=fee_pass_through,
    )


def _normalize_zero_decimal_checkout_amounts(
    tx: Optional[Dict[str, Any]],
    *,
    fallback_amount_usd: float = 0.0,
    fallback_currency: str = "USD",
) -> Dict[str, Any]:
    """Normalize suspicious zero-decimal currency amounts (XOF/XAF) to local units.

    Some legacy/manual transaction payloads may incorrectly persist USD-scale totals while
    marking currency as XOF/XAF. This helper safely auto-corrects those values for
    user/admin-facing confirmations and receipt generation.
    """
    tx = tx or {}
    currency = str(tx.get("currency") or fallback_currency or "USD").upper()
    method_raw = str(tx.get("payment_method") or tx.get("provider") or tx.get("gateway") or "").lower()
    is_fedapay = "fedapay" in method_raw

    amount_usd = _safe_float(tx.get("amount_usd", tx.get("amount", fallback_amount_usd)), fallback_amount_usd)
    fx_rate = _safe_float(tx.get("fx_rate", _fx_rate_for(currency, 1.0)), _fx_rate_for(currency, 1.0))
    subtotal_raw = _safe_float(tx.get("subtotal", tx.get("amount_local", tx.get("total_amount", amount_usd))), amount_usd)
    tax_raw = _safe_float(tx.get("tax_amount", 0), 0.0)
    fee_raw = _safe_float(tx.get("processing_fee", tx.get("fee", tx.get("fee_local", 0))), 0.0)
    total_raw = _safe_float(tx.get("total_amount", tx.get("amount_local", subtotal_raw + tax_raw + fee_raw)), subtotal_raw + tax_raw + fee_raw)
    fee_pct = _safe_float(tx.get("processing_fee_pct", tx.get("fee_pct", 0)), 0.0)
    tax_rate = _safe_float(tx.get("tax_rate", 0), 0.0)

    if currency not in ZERO_DECIMAL_CURRENCIES:
        return {
            "currency": currency,
            "subtotal": subtotal_raw,
            "tax_amount": tax_raw,
            "processing_fee": fee_raw,
            "total_amount": total_raw,
            "amount_local": _safe_float(tx.get("amount_local", total_raw), total_raw),
            "amount_gross": _safe_float(tx.get("amount_gross", subtotal_raw + tax_raw), subtotal_raw + tax_raw),
            "amount_net": _safe_float(tx.get("amount_net", max(total_raw - fee_raw, 0.0)), max(total_raw - fee_raw, 0.0)),
            "fx_rate": fx_rate,
            "corrected": False,
        }

    expected_subtotal = round(max(amount_usd, 0.0) * max(fx_rate, 1.0), 0)
    expected_tax = round(expected_subtotal * tax_rate, 0) if tax_rate > 0 else round(tax_raw * max(fx_rate, 1.0), 0) if (0 < tax_raw < 100 and expected_subtotal >= 500) else round(tax_raw, 0)

    expected_fee = round(fee_raw, 0)
    if fee_pct > 0:
        expected_fee = round(expected_subtotal * (fee_pct / 100.0), 0)
    elif fee_raw > 0 and fee_raw < 100 and expected_subtotal >= 500:
        expected_fee = round(fee_raw * max(fx_rate, 1.0), 0)
    elif fee_raw <= 0 and is_fedapay and expected_subtotal >= 500:
        expected_fee = round(expected_subtotal * 0.036, 0)

    suspicious_scale = (
        expected_subtotal >= 500
        and (
            subtotal_raw <= 100
            or total_raw <= 100
            or (tax_raw > 0 and tax_raw < 20 and expected_tax > 100)
            or (fee_raw > 0 and fee_raw < 20 and expected_fee > 100)
        )
    )

    if not suspicious_scale:
        return {
            "currency": currency,
            "subtotal": round(subtotal_raw, 0),
            "tax_amount": round(tax_raw, 0),
            "processing_fee": round(fee_raw, 0),
            "total_amount": round(total_raw, 0) if total_raw > 0 else round(subtotal_raw + tax_raw + fee_raw, 0),
            "amount_local": round(_safe_float(tx.get("amount_local", total_raw), total_raw), 0),
            "amount_gross": round(_safe_float(tx.get("amount_gross", subtotal_raw + tax_raw), subtotal_raw + tax_raw), 0),
            "amount_net": round(_safe_float(tx.get("amount_net", max(total_raw - fee_raw, 0.0)), max(total_raw - fee_raw, 0.0)), 0),
            "fx_rate": fx_rate,
            "corrected": False,
        }

    corrected_total = round(expected_subtotal + expected_tax + expected_fee, 0)
    corrected_gross = round(expected_subtotal + expected_tax, 0)
    corrected_net = max(corrected_total - expected_fee, 0)

    return {
        "currency": currency,
        "subtotal": expected_subtotal,
        "tax_amount": expected_tax,
        "processing_fee": expected_fee,
        "total_amount": corrected_total,
        "amount_local": corrected_total,
        "amount_gross": corrected_gross,
        "amount_net": corrected_net,
        "fx_rate": fx_rate,
        "corrected": True,
    }


def _detect_locale(tx: Optional[Dict[str, Any]] = None) -> str:
    return detect_payment_locale(tx)


def _is_french_context(tx: Optional[Dict[str, Any]] = None) -> bool:
    return _detect_locale(tx) == "fr"


def _receipt_product_type_label(_: Optional[str] = None) -> str:
    return "Digital Platform Access"


def _currency_symbol_for(code: str) -> str:
    upper = str(code or "USD").upper()
    return (SUPPORTED_CURRENCIES.get(upper) or {}).get("symbol", upper)


def _fx_rate_for(code: str, fallback: float = 1.0) -> float:
    return _safe_float((SUPPORTED_CURRENCIES.get(str(code or "USD").upper()) or {}).get("rate", fallback), fallback)


def _convert_from_usd(amount_usd: float, currency_code: str) -> float:
    currency = str(currency_code or "USD").upper()
    rate = _fx_rate_for(currency, 1.0)
    converted = _safe_float(amount_usd, 0.0) * rate
    return round(converted, 0) if currency in ZERO_DECIMAL_CURRENCIES else round(converted, 2)


def _minutes_since_iso(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
        return max(int(delta_seconds // 60), 0)
    except Exception:
        return None


def _build_processing_fee_breakdown(
    provider: str,
    currency: str,
    *,
    fee_pct: Optional[float] = None,
) -> Dict[str, Any]:
    provider_key = str(provider or "").strip().lower()
    ccy = str(currency or "USD").upper()

    if provider_key == "stripe":
        pct = 2.90
        fixed_fee = 0.30 if ccy == "USD" else 0.0
        formula = f"{pct:.2f}% + {_currency_symbol_for(ccy)} {fixed_fee:.2f}" if fixed_fee > 0 else f"{pct:.2f}%"
        return {
            "provider": "stripe",
            "provider_label": "Stripe",
            "rate_percent": pct,
            "fixed_fee": round(fixed_fee, 2),
            "fixed_fee_currency": ccy,
            "formula": formula,
            "source": "tax_compliance_engine",
        }

    if provider_key == "paypal":
        pct = 3.49
        fixed_fee = 0.49 if ccy == "USD" else 0.0
        formula = f"{pct:.2f}% + {_currency_symbol_for(ccy)} {fixed_fee:.2f}" if fixed_fee > 0 else f"{pct:.2f}%"
        return {
            "provider": "paypal",
            "provider_label": "PayPal",
            "rate_percent": pct,
            "fixed_fee": round(fixed_fee, 2),
            "fixed_fee_currency": ccy,
            "formula": formula,
            "source": "tax_compliance_engine",
        }

    pct = round(_safe_float(fee_pct, 0.0), 2)
    formula = f"{pct:.2f}%"
    return {
        "provider": "fedapay",
        "provider_label": "FedaPay",
        "rate_percent": pct,
        "fixed_fee": 0.0,
        "fixed_fee_currency": ccy,
        "formula": formula,
        "source": "fedapay_policy_contract",
    }


async def _compute_checkout_breakdown(
    user,
    req: Request,
    payload: CheckoutPreviewRequest,
    *,
    enforce_methods: tuple[str, ...] = ("stripe", "paypal", "fedapay"),
) -> Dict[str, Any]:
    method = str(payload.payment_method or "stripe").strip().lower()
    if method not in enforce_methods:
        raise HTTPException(status_code=400, detail=f"Invalid payment method. Use one of: {', '.join(enforce_methods)}")

    fee_ui_visibility = resolve_checkout_fee_visibility_policy(
        method,
        is_admin=bool(getattr(user, "is_admin", False)),
    )

    plan = await require_paid_subscription_plan(payload.plan_id)

    amount_usd = _safe_float(plan["monthly_price"] if payload.billing_period == "monthly" else plan["yearly_price"], 0.0)
    product_type = resolve_product_type(payload.plan_id, payload.product_type)
    localization = await resolve_payment_localization_context(
        db=db,
        request=req,
        user=user,
        country_code=payload.country_code,
        state_code=payload.state_code,
        postal_code=payload.postal_code,
        requested_currency=payload.currency,
        requested_language=payload.preferred_language,
        browser_language=payload.browser_language,
        browser_languages=payload.browser_languages,
    )
    jurisdiction = localization.get("jurisdiction", {})
    requested_currency = str(payload.currency or localization.get("resolved_currency") or "USD").upper()

    def _base_preview(public_currency: str, *, charge_currency: Optional[str] = None, fx_rate: float = 1.0) -> Dict[str, Any]:
        fallback_applied = bool(charge_currency and requested_currency and charge_currency != requested_currency)
        return {
            "requested_currency": requested_currency,
            "currency": public_currency,
            "charge_currency": charge_currency or public_currency,
            "currency_symbol": _currency_symbol_for(public_currency),
            "fx_rate": fx_rate,
            "fx_base_currency": "USD",
            "base_amount_usd": round(amount_usd, 2),
            "localization_context": {
                "resolved_language": localization.get("resolved_language", "en"),
                "resolved_currency": localization.get("resolved_currency", requested_currency),
                "jurisdiction": jurisdiction,
                "confidence": localization.get("confidence", 0),
                "source_priority": localization.get("source_priority", {}),
                "validation_status": localization.get("validation_status", "deterministic_only"),
                "requires_ai_validation": localization.get("requires_ai_validation", False),
            },
            "currency_fallback_applied": fallback_applied,
            "currency_resolution_note": (
                f"Checkout is charged in {charge_currency} because {requested_currency} is not supported on this provider."
                if fallback_applied and charge_currency
                else f"FX normalized from USD using current rate {fx_rate}."
            ),
        }

    if method == "stripe":
        currency_info = SUPPORTED_CURRENCIES.get(requested_currency)
        checkout_currency = requested_currency if currency_info and currency_info.get("stripe_supported") else "USD"
        subtotal_local = _convert_from_usd(amount_usd, checkout_currency)
        fx_rate = _fx_rate_for(checkout_currency, 1.0)

        tax_quote = await calculate_tax_quote(
            provider="stripe",
            subtotal=float(subtotal_local),
            currency=checkout_currency,
            country_code=jurisdiction.get("country"),
            state_code=jurisdiction.get("state"),
            postal_code=jurisdiction.get("postal_code"),
            product_type=product_type,
        )
        processing_fee = estimate_processing_fee("stripe", tax_quote.get("amount_gross", subtotal_local), checkout_currency)
        financials = build_financial_totals(
            subtotal=tax_quote.get("subtotal", subtotal_local),
            tax_amount=tax_quote.get("tax_amount", 0.0),
            processing_fee=processing_fee,
            fee_pass_through=True,
        )
        fee_breakdown = _build_processing_fee_breakdown("stripe", checkout_currency)
        preview = {
            "payment_method": "stripe",
            "provider_display_name": "Stripe",
            "subtotal": round(_safe_float(financials.get("subtotal", 0), 0.0), 2),
            "tax_fee": round(_safe_float(financials.get("tax_amount", 0), 0.0), 2),
            "processing_fee": round(_safe_float(financials.get("processing_fee", 0), 0.0), 2),
            "processing_fee_pct": round(_safe_float(fee_breakdown.get("rate_percent", 0), 0.0), 2),
            "gross_amount": round(_safe_float(financials.get("amount_gross", 0), 0.0), 2),
            "net_amount": round(_safe_float(financials.get("amount_net", 0), 0.0), 2),
            "total_amount": round(_safe_float(financials.get("total_amount", 0), 0.0), 2),
            "tax_rate_pct": round(_safe_float(tax_quote.get("tax_rate", 0), 0.0) * 100, 2),
            "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
            "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
            "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
            "product_type": tax_quote.get("product_type", product_type),
            "fee_visibility_note": "Applicable Tax and Payment Processing Fee are included in Total You Pay." if not fee_ui_visibility.get("hide_customer_provider_fee_lines") else "Final total includes all applicable taxes and provider fees.",
            "processing_fee_breakdown": fee_breakdown,
            "processing_fee_formula": fee_breakdown.get("formula", ""),
            "fee_policy_source": fee_breakdown.get("source", "tax_compliance_engine"),
            "fee_ui_visibility": fee_ui_visibility,
            "internal": {
                "financials": financials,
                "tax_quote": tax_quote,
                "checkout_currency": checkout_currency.lower(),
            },
        }
        preview.update(_base_preview(checkout_currency, fx_rate=fx_rate))
        return preview

    if method == "paypal":
        checkout_currency = requested_currency if requested_currency in PAYPAL_SUPPORTED_CURRENCIES else "USD"
        subtotal_local = _convert_from_usd(amount_usd, checkout_currency)
        fx_rate = _fx_rate_for(checkout_currency, 1.0)
        tax_quote = await calculate_tax_quote(
            provider="paypal",
            subtotal=float(subtotal_local),
            currency=checkout_currency,
            country_code=jurisdiction.get("country"),
            state_code=jurisdiction.get("state"),
            postal_code=jurisdiction.get("postal_code"),
            product_type=product_type,
        )
        processing_fee = estimate_processing_fee("paypal", tax_quote.get("amount_gross", subtotal_local), checkout_currency)
        financials = build_financial_totals(
            subtotal=tax_quote.get("subtotal", subtotal_local),
            tax_amount=tax_quote.get("tax_amount", 0.0),
            processing_fee=processing_fee,
            fee_pass_through=True,
        )
        fee_breakdown = _build_processing_fee_breakdown("paypal", checkout_currency)
        preview = {
            "payment_method": "paypal",
            "provider_display_name": "PayPal",
            "subtotal": round(_safe_float(financials.get("subtotal", 0), 0.0), 2),
            "tax_fee": round(_safe_float(financials.get("tax_amount", 0), 0.0), 2),
            "processing_fee": round(_safe_float(financials.get("processing_fee", 0), 0.0), 2),
            "processing_fee_pct": round(_safe_float(fee_breakdown.get("rate_percent", 0), 0.0), 2),
            "gross_amount": round(_safe_float(financials.get("amount_gross", 0), 0.0), 2),
            "net_amount": round(_safe_float(financials.get("amount_net", 0), 0.0), 2),
            "total_amount": round(_safe_float(financials.get("total_amount", 0), 0.0), 2),
            "tax_rate_pct": round(_safe_float(tax_quote.get("tax_rate", 0), 0.0) * 100, 2),
            "tax_provider": tax_quote.get("tax_provider", "internal_rules_engine"),
            "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
            "jurisdiction": tax_quote.get("jurisdiction", jurisdiction),
            "product_type": tax_quote.get("product_type", product_type),
            "fee_visibility_note": "Applicable Tax and Payment Processing Fee are included in Total You Pay." if not fee_ui_visibility.get("hide_customer_provider_fee_lines") else "Final total includes all applicable taxes and provider fees.",
            "processing_fee_breakdown": fee_breakdown,
            "processing_fee_formula": fee_breakdown.get("formula", ""),
            "fee_policy_source": fee_breakdown.get("source", "tax_compliance_engine"),
            "fee_ui_visibility": fee_ui_visibility,
            "internal": {
                "financials": financials,
                "tax_quote": tax_quote,
                "checkout_currency": checkout_currency.lower(),
            },
        }
        preview.update(_base_preview(checkout_currency, fx_rate=fx_rate))
        return preview

    # method == fedapay
    selected_currency = requested_currency if requested_currency in MOBILE_MONEY_FX else str(localization.get("resolved_currency") or "XOF").upper()
    if selected_currency not in MOBILE_MONEY_FX:
        selected_currency = "XOF"
    fx_rate = _safe_float(MOBILE_MONEY_FX.get(selected_currency, _fx_rate_for(selected_currency, 605.0)), 605.0)
    tax_quote = await calculate_tax_quote(
        provider="fedapay",
        subtotal=float(amount_usd),
        currency="USD",
        country_code=jurisdiction.get("country"),
        state_code=jurisdiction.get("state"),
        postal_code=jurisdiction.get("postal_code"),
        product_type=product_type,
    )
    usd_tax = _safe_float(tax_quote.get("tax_amount", 0), 0.0)
    subtotal_local = round(amount_usd * fx_rate, 0)
    tax_local = round(usd_tax * fx_rate, 0)
    fedapay_policy = await get_fedapay_policy(db)
    fee_pct = _resolve_fedapay_fee_pct(
        fedapay_policy,
        jurisdiction.get("country"),
        payload.mobile_provider,
    )
    amount_gross_local = round(subtotal_local + tax_local, 0)
    processing_fee = estimate_processing_fee(
        "fedapay",
        amount_gross_local,
        selected_currency,
        context={"fee_pct": fee_pct},
    )
    processing_fee_policy_ok = bool(_safe_float(fee_pct, 0.0) > 0 and _safe_float(processing_fee, 0.0) > 0)
    financials = build_financial_totals(
        subtotal=float(subtotal_local),
        tax_amount=float(tax_local),
        processing_fee=float(processing_fee),
        fee_pass_through=True,
    )
    fedapay_breakdown = _build_processing_fee_breakdown("fedapay", selected_currency, fee_pct=fee_pct)
    jurisdiction_display = dict(tax_quote.get("jurisdiction", jurisdiction) or {})
    if str(jurisdiction_display.get("country") or "").strip().upper() == "BJ":
        jurisdiction_display["country"] = "US"

    preview = {
        "payment_method": "fedapay",
        "provider_display_name": "FedaPay",
        "subtotal": round(_safe_float(financials.get("subtotal", 0), 0.0), 0),
        "tax_fee": round(_safe_float(financials.get("tax_amount", 0), 0.0), 0),
        "processing_fee": round(_safe_float(financials.get("processing_fee", 0), 0.0), 0),
        "processing_fee_pct": round(_safe_float(fee_pct, 0.0), 2),
        "gross_amount": round(_safe_float(financials.get("amount_gross", 0), 0.0), 0),
        "net_amount": round(_safe_float(financials.get("amount_net", 0), 0.0), 0),
        "total_amount": round(_safe_float(financials.get("total_amount", 0), 0.0), 0),
        "tax_rate_pct": round(_safe_float(tax_quote.get("tax_rate", 0), 0.0) * 100, 2),
        "tax_provider": tax_quote.get("tax_provider", "fedapay_fixed_rate"),
        "tax_engine": tax_quote.get("tax_engine", "fallback_internal"),
        "jurisdiction": jurisdiction_display,
        "product_type": tax_quote.get("product_type", product_type),
        "fee_visibility_note": "Fixed 8.25% tax and FedaPay processing fee are included and shown before payment redirect." if not fee_ui_visibility.get("hide_customer_provider_fee_lines") else "Final total includes fixed tax and provider fees.",
        "fedapay_policy_source": fedapay_policy.get("source", "contract_seed"),
        "fedapay_policy_updated_at": fedapay_policy.get("updated_at"),
        "fedapay_policy_last_synced_minutes_ago": _minutes_since_iso(fedapay_policy.get("updated_at")),
        "supported_cards": fedapay_policy.get("channels", {}).get("card", {}).get("supported_cards", ["mastercard", "visa"]),
        "processing_fee_policy_ok": processing_fee_policy_ok,
        "processing_fee_breakdown": fedapay_breakdown,
        "processing_fee_formula": fedapay_breakdown.get("formula", ""),
        "fee_policy_source": fedapay_policy.get("source", "contract_seed"),
        "fee_ui_visibility": fee_ui_visibility,
        "internal": {
            "financials": financials,
            "tax_quote": tax_quote,
            "checkout_currency": selected_currency.lower(),
            "fedapay_policy": {
                "source": fedapay_policy.get("source"),
                "updated_at": fedapay_policy.get("updated_at"),
            },
        },
    }
    preview.update(_base_preview(selected_currency, fx_rate=fx_rate))
    if isinstance(preview.get("localization_context"), dict):
        preview["localization_context"]["jurisdiction"] = jurisdiction_display
    return preview
