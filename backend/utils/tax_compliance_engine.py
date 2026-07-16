"""Unified tax compliance + financial ledger utilities for multi-provider payments."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

import httpx


ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "XOF", "XAF"}

DEFAULT_PRODUCT_TYPE_BY_PLAN = {
    "basic": "education_digital_service",
    "premium": "education_digital_service",
    "free": "education_digital_service",
}

# Initial ruleset requested by user (US states + EU VAT + UK/CA/AU/NG/ZA) + BJ for FedaPay.
INTERNAL_TAX_RULES: Dict[str, Dict[str, Decimal]] = {
    "US": {
        "AL": Decimal("0.04"),
        "AK": Decimal("0.00"),
        "AZ": Decimal("0.056"),
        "AR": Decimal("0.065"),
        "CA": Decimal("0.0725"),
        "CO": Decimal("0.029"),
        "CT": Decimal("0.0635"),
        "DE": Decimal("0.00"),
        "FL": Decimal("0.06"),
        "GA": Decimal("0.04"),
        "HI": Decimal("0.04"),
        "IA": Decimal("0.06"),
        "ID": Decimal("0.06"),
        "IL": Decimal("0.0625"),
        "IN": Decimal("0.07"),
        "KS": Decimal("0.065"),
        "KY": Decimal("0.06"),
        "LA": Decimal("0.0445"),
        "MA": Decimal("0.0625"),
        "MD": Decimal("0.06"),
        "ME": Decimal("0.055"),
        "MI": Decimal("0.06"),
        "MN": Decimal("0.06875"),
        "MO": Decimal("0.04225"),
        "MS": Decimal("0.07"),
        "MT": Decimal("0.00"),
        "NC": Decimal("0.0475"),
        "ND": Decimal("0.05"),
        "NE": Decimal("0.055"),
        "NH": Decimal("0.00"),
        "NJ": Decimal("0.06625"),
        "NM": Decimal("0.05125"),
        "NV": Decimal("0.0685"),
        "NY": Decimal("0.04"),
        "OH": Decimal("0.0575"),
        "OK": Decimal("0.045"),
        "OR": Decimal("0.00"),
        "PA": Decimal("0.06"),
        "RI": Decimal("0.07"),
        "SC": Decimal("0.06"),
        "SD": Decimal("0.045"),
        "TN": Decimal("0.07"),
        "TX": Decimal("0.0625"),
        "UT": Decimal("0.061"),
        "VA": Decimal("0.053"),
        "VT": Decimal("0.06"),
        "WA": Decimal("0.065"),
        "WI": Decimal("0.05"),
        "WV": Decimal("0.06"),
        "WY": Decimal("0.04"),
        "": Decimal("0.00"),
    },
    "EU": {
        "AT": Decimal("0.20"),
        "BE": Decimal("0.21"),
        "BG": Decimal("0.20"),
        "CY": Decimal("0.19"),
        "CZ": Decimal("0.21"),
        "DE": Decimal("0.19"),
        "DK": Decimal("0.25"),
        "EE": Decimal("0.22"),
        "ES": Decimal("0.21"),
        "FI": Decimal("0.24"),
        "FR": Decimal("0.20"),
        "GR": Decimal("0.24"),
        "HR": Decimal("0.25"),
        "HU": Decimal("0.27"),
        "IE": Decimal("0.23"),
        "IT": Decimal("0.22"),
        "LT": Decimal("0.21"),
        "LU": Decimal("0.17"),
        "LV": Decimal("0.21"),
        "MT": Decimal("0.18"),
        "NL": Decimal("0.21"),
        "PL": Decimal("0.23"),
        "PT": Decimal("0.23"),
        "RO": Decimal("0.19"),
        "SE": Decimal("0.25"),
        "SI": Decimal("0.22"),
        "SK": Decimal("0.20"),
    },
    "GB": {"": Decimal("0.20")},
    "UK": {"": Decimal("0.20")},
    "CA": {
        "AB": Decimal("0.05"),
        "BC": Decimal("0.12"),
        "MB": Decimal("0.12"),
        "NB": Decimal("0.15"),
        "NL": Decimal("0.15"),
        "NS": Decimal("0.15"),
        "NT": Decimal("0.05"),
        "NU": Decimal("0.05"),
        "ON": Decimal("0.13"),
        "PE": Decimal("0.15"),
        "QC": Decimal("0.14975"),
        "SK": Decimal("0.11"),
        "YT": Decimal("0.05"),
        "": Decimal("0.05"),
    },
    "AU": {"": Decimal("0.10")},
    "NG": {"": Decimal("0.075")},
    "ZA": {"": Decimal("0.15")},
    "BJ": {"": Decimal("0.18")},
}

EU_COUNTRIES = set(INTERNAL_TAX_RULES["EU"].keys())


def _d(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_jurisdiction(country_code: Optional[str], state_code: Optional[str]) -> tuple[str, str]:
    country = (country_code or "").strip().upper()
    state = (state_code or "").strip().upper()
    if country in EU_COUNTRIES:
        return country, state
    if not country:
        return "US", state
    return country, state


def resolve_internal_tax_rate(country_code: Optional[str], state_code: Optional[str]) -> Decimal:
    country, state = normalize_jurisdiction(country_code, state_code)

    if country in EU_COUNTRIES:
        return INTERNAL_TAX_RULES["EU"].get(country, Decimal("0.20"))

    country_rules = INTERNAL_TAX_RULES.get(country)
    if country_rules:
        if state and state in country_rules:
            return country_rules[state]
        return country_rules.get("", Decimal("0.00"))

    return Decimal("0.00")


def resolve_product_type(plan_id: str, explicit_product_type: Optional[str] = None) -> str:
    if explicit_product_type:
        return explicit_product_type.strip().lower()
    return DEFAULT_PRODUCT_TYPE_BY_PLAN.get((plan_id or "free").lower(), "education_digital_service")


async def calculate_tax_quote(
    *,
    provider: str,
    subtotal: float,
    currency: str,
    country_code: Optional[str],
    state_code: Optional[str],
    postal_code: Optional[str],
    product_type: str,
) -> Dict[str, Any]:
    """Unified tax abstraction: use provider tax service if available, else internal rules fallback."""
    provider_key = (provider or "internal").lower()
    currency_code = (currency or "USD").upper()
    subtotal_d = _q2(_d(subtotal))
    country, state = normalize_jurisdiction(country_code, state_code)

    # Business rule override: FedaPay has fixed 8.25% tax, no jurisdiction tax matrix.
    if provider_key in {"fedapay", "mobile_money_fedapay", "fedapay_card"} or "fedapay" in provider_key:
        fedapay_rate = Decimal("0.0825")
        tax_amount = _q2(subtotal_d * fedapay_rate)
        amount_gross = _q2(subtotal_d + tax_amount)
        return {
            "tax_provider": "fedapay_fixed_rate",
            "tax_engine": "provider_policy_override",
            "jurisdiction": {"country": country or "N/A", "state": "", "postal_code": ""},
            "product_type": product_type,
            "tax_rate": float(fedapay_rate),
            "tax_amount": float(tax_amount),
            "subtotal": float(subtotal_d),
            "amount_gross": float(amount_gross),
            "tax_breakdown": [
                {
                    "jurisdiction": "FEDAPAY_FIXED",
                    "tax_type": "fixed_transaction_tax",
                    "rate": float(fedapay_rate),
                    "amount": float(tax_amount),
                    "note": "Fixed 8.25% tax applied per transaction",
                }
            ],
        }

    if provider_key == "stripe":
        stripe_secret = os.environ.get("STRIPE_API_KEY", "")
        if stripe_secret and country:
            try:
                quote = await _stripe_tax_quote(
                    stripe_secret=stripe_secret,
                    subtotal=subtotal_d,
                    currency=currency_code,
                    country=country,
                    state=state,
                    postal_code=(postal_code or "").strip(),
                    product_type=product_type,
                )
                # If provider returns zero tax for a jurisdiction that should be taxed,
                # fallback to internal rule engine to avoid missing tax at checkout.
                provider_tax = _d((quote or {}).get("tax_amount", 0))
                fallback_rate = resolve_internal_tax_rate(country, state)
                should_force_fallback = bool(
                    quote
                    and provider_tax <= Decimal("0")
                    and fallback_rate > Decimal("0")
                )
                if quote and not should_force_fallback:
                    return quote
            except Exception:
                pass

    rate = resolve_internal_tax_rate(country, state)
    tax_amount = _q2(subtotal_d * rate)
    amount_gross = _q2(subtotal_d + tax_amount)

    return {
        "tax_provider": "internal_rules_engine",
        "tax_engine": "fallback_internal",
        "jurisdiction": {"country": country, "state": state, "postal_code": postal_code or ""},
        "product_type": product_type,
        "tax_rate": float(rate),
        "tax_amount": float(tax_amount),
        "subtotal": float(subtotal_d),
        "amount_gross": float(amount_gross),
        "tax_breakdown": [
            {
                "jurisdiction": f"{country}-{state}" if state else country,
                "tax_type": "vat" if country in EU_COUNTRIES or country in {"GB", "UK"} else "sales_tax",
                "rate": float(rate),
                "amount": float(tax_amount),
            }
        ],
    }


async def _stripe_tax_quote(
    *,
    stripe_secret: str,
    subtotal: Decimal,
    currency: str,
    country: str,
    state: str,
    postal_code: str,
    product_type: str,
) -> Optional[Dict[str, Any]]:
    smallest_unit_multiplier = 1 if currency in ZERO_DECIMAL_CURRENCIES else 100
    amount_smallest = int((subtotal * Decimal(smallest_unit_multiplier)).to_integral_value(rounding=ROUND_HALF_UP))

    form = {
        "currency": currency.lower(),
        "tax_date": str(int(time.time())),
        "line_items[0][amount]": str(amount_smallest),
        "line_items[0][reference]": f"realaicoach-{product_type}",
        "line_items[0][tax_behavior]": "exclusive",
        "customer_details[address][country]": country,
        "customer_details[address_source]": "billing",
    }
    if state:
        form["customer_details[address][state]"] = state
    if postal_code:
        form["customer_details[address][postal_code]"] = postal_code

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.stripe.com/v1/tax/calculations",
            data=form,
            auth=(stripe_secret, ""),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code not in (200, 201):
            return None
        data = response.json() if isinstance(response.json(), dict) else {}

    tax_smallest = int(data.get("tax_amount_exclusive", 0) or 0)
    gross_smallest = int(data.get("amount_total", amount_smallest + tax_smallest) or (amount_smallest + tax_smallest))
    tax_amount = _q2(Decimal(tax_smallest) / Decimal(smallest_unit_multiplier))
    amount_gross = _q2(Decimal(gross_smallest) / Decimal(smallest_unit_multiplier))
    subtotal_q = _q2(Decimal(amount_smallest) / Decimal(smallest_unit_multiplier))
    rate = (tax_amount / subtotal_q) if subtotal_q > 0 else Decimal("0")

    return {
        "tax_provider": "stripe_tax",
        "tax_engine": "provider_native",
        "jurisdiction": {"country": country, "state": state, "postal_code": postal_code},
        "product_type": product_type,
        "tax_rate": float(_q2(rate)),
        "tax_amount": float(tax_amount),
        "subtotal": float(subtotal_q),
        "amount_gross": float(amount_gross),
        "tax_breakdown": [
            {
                "jurisdiction": f"{country}-{state}" if state else country,
                "tax_type": "stripe_tax",
                "rate": float(_q2(rate)),
                "amount": float(tax_amount),
            }
        ],
        "provider_tax_calculation_id": data.get("id"),
    }


def estimate_processing_fee(provider: str, amount_gross: float, currency: str, context: Optional[Dict[str, Any]] = None) -> float:
    context = context or {}
    provider_key = (provider or "").lower()
    gross = _q2(_d(amount_gross))
    ccy = (currency or "USD").upper()

    if provider_key in {"stripe", "stripe_tax"}:
        pct = Decimal("0.029")
        flat = Decimal("0.30") if ccy == "USD" else Decimal("0")
        return float(_q2(gross * pct + flat))
    if provider_key in {"paypal", "paypal_js", "paypal_tax"}:
        pct = Decimal("0.0349")
        flat = Decimal("0.49") if ccy == "USD" else Decimal("0")
        return float(_q2(gross * pct + flat))
    if provider_key in {"fedapay", "mobile_money_fedapay", "fedapay_card"} or "fedapay" in provider_key:
        fee_pct = _d(context.get("fee_pct", 0.0)) / Decimal("100")
        return float(_q2(gross * fee_pct))
    if provider_key in {"iap_apple", "iap_google", "apple", "google"}:
        store_rate = _d(context.get("store_fee_rate", 0.30))
        return float(_q2(gross * store_rate))
    return 0.0


def build_financial_totals(*, subtotal: float, tax_amount: float, processing_fee: float, fee_pass_through: bool = False) -> Dict[str, float]:
    subtotal_d = _q2(_d(subtotal))
    tax_d = _q2(_d(tax_amount))
    fee_d = _q2(_d(processing_fee))
    amount_gross = _q2(subtotal_d + tax_d)
    total_charged = _q2(amount_gross + fee_d) if fee_pass_through else amount_gross
    amount_net = _q2(total_charged - fee_d)
    if amount_net < 0:
        amount_net = Decimal("0.00")
    return {
        "subtotal": float(subtotal_d),
        "tax_amount": float(tax_d),
        "processing_fee": float(fee_d),
        "amount_gross": float(amount_gross),
        "total_amount": float(total_charged),
        "amount_net": float(amount_net),
    }


async def log_tax_calculation(db, *, transaction_id: str, provider: str, user_id: str, payload: Dict[str, Any]) -> None:
    await db.tax_calculation_logs.insert_one(
        {
            "log_id": f"taxlog_{hashlib.sha1(f'{transaction_id}_{time.time()}'.encode()).hexdigest()[:14]}",
            "transaction_id": transaction_id,
            "provider": provider,
            "user_id": user_id,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def append_financial_ledger_entry(db, *, event_type: str, transaction_id: str, provider: str, user_id: str, payload: Dict[str, Any]) -> None:
    latest = await db.financial_ledger_entries.find_one({}, {"_id": 0, "sequence": 1, "entry_hash": 1}, sort=[("sequence", -1)]) or {}
    sequence = int(latest.get("sequence", 0) or 0) + 1
    prev_hash = latest.get("entry_hash", "GENESIS")
    created_at = datetime.now(timezone.utc).isoformat()
    hash_input = json.dumps(
        {
            "sequence": sequence,
            "prev_hash": prev_hash,
            "event_type": event_type,
            "transaction_id": transaction_id,
            "provider": provider,
            "user_id": user_id,
            "payload": payload,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    entry_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    await db.financial_ledger_entries.insert_one(
        {
            "sequence": sequence,
            "event_type": event_type,
            "transaction_id": transaction_id,
            "provider": provider,
            "user_id": user_id,
            "payload": payload,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "created_at": created_at,
        }
    )
