"""Shared pricing guard helpers for payments routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from bson import ObjectId
from fastapi import HTTPException

from .db import db, logger
from .payments_catalog import get_subscription_plan_from_gps


def normalize_billing_period(period_raw: Any) -> str:
    period = str(period_raw or "monthly").strip().lower()
    if period in {"year", "annual", "annually", "yearly"}:
        return "yearly"
    return "monthly"


def safe_amount_value(raw: Any) -> float:
    try:
        return float(raw or 0)
    except Exception:
        return 0.0


_DOCUMENT_PRICING_CONTEXTS = {
    "receipt_pdf",
    "invoice_pdf",
    "receipt_html",
    "invoice_html",
    "verify_document",
    "verify_send_email",
    "email_receipt",
    "email_receipt_number",
    "email_invoice_pdf",
    "pdf_generation_receipt",
    "pdf_generation_invoice",
}


def extract_payment_amount_for_plan_validation(payment: dict, *, context: str = "") -> float:
    normalized_context = str(context or "").strip().lower()
    if normalized_context in _DOCUMENT_PRICING_CONTEXTS:
        provider = str(payment.get("provider") or payment.get("payment_method") or "").lower()
        if provider in {"iap_google", "iap_apple", "google_iap", "apple_iap", "google", "apple"}:
            keys = (
                "base_plan_price",
                "amount",
                "original_usd_amount",
                "amount_usd",
                "subtotal",
                "amount_gross",
                "total_amount",
            )
        else:
            keys = ("amount", "original_usd_amount", "amount_usd", "subtotal", "amount_gross", "total_amount")
    else:
        keys = ("amount_gross", "total_amount", "amount", "subtotal")

    for key in keys:
        value = safe_amount_value(payment.get(key))
        if value > 0:
            return value
    return safe_amount_value(payment.get("amount"))


async def resolve_plan_pricing_snapshot(plan_id_raw: Any, billing_period_raw: Any) -> dict:
    plan_id = str(plan_id_raw or "").strip().lower()
    if plan_id not in {"basic", "premium"}:
        raise ValueError(f"unsupported_plan_for_strict_validation:{plan_id or 'missing'}")
    plan = await get_subscription_plan_from_gps(plan_id)
    if not plan:
        raise ValueError(f"plan_not_found:{plan_id}")
    billing_period = normalize_billing_period(billing_period_raw)
    expected_amount = safe_amount_value(plan.get("monthly_price") if billing_period == "monthly" else plan.get("yearly_price"))
    if expected_amount <= 0:
        raise ValueError(f"invalid_plan_price:{plan_id}:{billing_period}")
    return {
        "plan_id": plan_id,
        "plan_name": str(plan.get("name") or plan_id.title()),
        "billing_period": billing_period,
        "expected_amount": round(expected_amount, 2),
    }


def price_mismatch_alert_payload(*, payment: dict, context: str, reason: str, expected_amount: float, actual_amount: float) -> dict:
    return {
        "alert_id": f"pmae_{uuid.uuid4().hex[:16]}",
        "context": context,
        "reason": reason,
        "plan_id": str(payment.get("plan_id") or "").lower(),
        "billing_period": normalize_billing_period(payment.get("billing_period")),
        "expected_amount": round(expected_amount, 2),
        "actual_amount": round(actual_amount, 2),
        "payment_id": payment.get("payment_id") or payment.get("id") or payment.get("transaction_id") or "",
        "user_id": payment.get("user_id") or "",
        "currency": str(payment.get("currency") or "USD").upper(),
        "status": "open",
        "acked_at": None,
        "acked_by": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def log_price_mismatch_alert(*, payment: dict, context: str, reason: str, expected_amount: float, actual_amount: float) -> None:
    payload = price_mismatch_alert_payload(
        payment=payment,
        context=context,
        reason=reason,
        expected_amount=expected_amount,
        actual_amount=actual_amount,
    )
    logger.error("[pricing-guard] %s", payload)
    try:
        await db.pricing_mismatch_alert_events.insert_one(payload)
    except Exception as exc:
        logger.error("[pricing-guard] failed to persist alert: %s", exc)


async def assert_plan_pricing_or_block(payment: dict, *, context: str) -> dict:
    try:
        snapshot = await resolve_plan_pricing_snapshot(payment.get("plan_id"), payment.get("billing_period"))
    except ValueError as exc:
        actual_amount = extract_payment_amount_for_plan_validation(payment, context=context)
        await log_price_mismatch_alert(
            payment=payment,
            context=context,
            reason=str(exc),
            expected_amount=0.0,
            actual_amount=actual_amount,
        )
        raise HTTPException(status_code=409, detail=f"Pricing validation blocked: {exc}")

    actual_amount = extract_payment_amount_for_plan_validation(payment, context=context)
    expected_amount = snapshot["expected_amount"]
    if abs(actual_amount - expected_amount) > 0.01:
        await log_price_mismatch_alert(
            payment=payment,
            context=context,
            reason="amount_mismatch",
            expected_amount=expected_amount,
            actual_amount=actual_amount,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pricing mismatch blocked for {snapshot['plan_name']} {snapshot['billing_period']} plan. "
                f"Expected ${expected_amount:.2f}, got ${actual_amount:.2f}."
            ),
        )
    return snapshot


def assert_plan_pricing_or_raise_sync(payment: dict, *, context: str) -> dict:
    raise RuntimeError("Synchronous pricing validation is disabled; use assert_plan_pricing_or_block for GPS-backed plan pricing.")


def apply_canonical_plan_pricing(payment: dict, snapshot: dict) -> dict:
    canonical = dict(payment)
    canonical_amount = snapshot["expected_amount"]
    canonical["plan_id"] = snapshot["plan_id"]
    canonical["billing_period"] = snapshot["billing_period"]
    canonical["amount"] = canonical_amount
    if canonical.get("subtotal") is None:
        canonical["subtotal"] = canonical_amount
    if canonical.get("amount_gross") is None:
        canonical["amount_gross"] = canonical_amount
    if canonical.get("total_amount") is None:
        canonical["total_amount"] = canonical_amount
    return canonical


def pricing_mismatch_event_query(event_id: str) -> dict:
    normalized = str(event_id or "").strip()
    if not normalized:
        return {"alert_id": "__invalid_event_id__"}
    try:
        return {"$or": [{"alert_id": normalized}, {"_id": ObjectId(normalized)}]}
    except Exception:
        return {"alert_id": normalized}


def format_pricing_mismatch_event(doc: dict) -> dict:
    alert_id = str(doc.get("alert_id") or "").strip()
    mongo_id = doc.get("_id")
    event_id = alert_id or (str(mongo_id) if mongo_id is not None else "")
    status = str(doc.get("status") or "").strip().lower()
    if status not in {"open", "acknowledged"}:
        status = "acknowledged" if doc.get("acked_at") else "open"
    return {
        "event_id": event_id,
        "alert_id": alert_id,
        "status": status,
        "context": str(doc.get("context") or ""),
        "reason": str(doc.get("reason") or ""),
        "plan_id": str(doc.get("plan_id") or ""),
        "billing_period": str(doc.get("billing_period") or ""),
        "expected_amount": float(doc.get("expected_amount") or 0),
        "actual_amount": float(doc.get("actual_amount") or 0),
        "payment_id": str(doc.get("payment_id") or ""),
        "user_id": str(doc.get("user_id") or ""),
        "currency": str(doc.get("currency") or "USD"),
        "created_at": doc.get("created_at"),
        "acked_at": doc.get("acked_at"),
        "acked_by": doc.get("acked_by"),
    }