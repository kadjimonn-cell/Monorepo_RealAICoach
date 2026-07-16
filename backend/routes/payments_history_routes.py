"""Payment history route aggregator and compatibility aliases."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from .db import db
from . import payments_history_shared as _history_shared
from . import payments_history_bulk_routes as _bulk_routes
from . import payments_history_document_routes as _document_routes
from . import payments_history_tax_routes as _tax_routes


router = APIRouter()
router.include_router(_tax_routes.router)
router.include_router(_document_routes.router)
router.include_router(_bulk_routes.router)


def _normalize_gateway_key(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if "paypal" in value:
        return "paypal"
    if "feda" in value or "mobile" in value:
        return "fedapay"
    if "stripe" in value or "card" in value:
        return "stripe"
    return "unknown"


def _resolve_provider_label(gateway_key: str, fallback: str = "") -> str:
    if gateway_key == "paypal":
        return "PayPal"
    if gateway_key == "fedapay":
        return "FedaPay"
    if gateway_key == "stripe":
        return "Stripe"
    resolved_fallback = str(fallback or "").strip()
    return resolved_fallback or "Payment Gateway"


def _resolve_document_id(row: dict) -> str:
    candidates = [
        row.get("payment_id"),
        row.get("transaction_id"),
        row.get("id"),
        row.get("session_id"),
        row.get("tx_id"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _serialize_payment_history_row(row: dict) -> dict:
    serialized = dict(row or {})
    if serialized.get("amount") is None:
        serialized["amount"] = 0

    gateway_key = _normalize_gateway_key(
        serialized.get("gateway")
        or serialized.get("provider")
        or serialized.get("payment_method")
        or ""
    )
    fallback_label = (
        serialized.get("provider")
        or serialized.get("gateway")
        or serialized.get("payment_method")
        or ""
    )
    document_id = _resolve_document_id(serialized)

    serialized["gateway_key"] = gateway_key
    serialized["provider_display_name"] = _resolve_provider_label(gateway_key, str(fallback_label))
    serialized["receipt_document_id"] = document_id
    serialized["receipt_download_url"] = f"/api/payments/receipt/{document_id}/pdf" if document_id else ""
    serialized["receipt_fallback_url"] = (
        f"/payment-document-v2?payment_id={document_id}&doc=receipt&action=download"
        if document_id else ""
    )
    serialized["invoice_download_url"] = f"/api/payments/invoice/{document_id}/pdf" if document_id else ""
    return serialized


@router.get("/payments/history")
async def get_payment_history(request: Request):
    user = await _history_shared._get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    requested_gateway = _normalize_gateway_key(request.query_params.get("gateway") or "")
    apply_gateway_filter = requested_gateway in {"stripe", "paypal", "fedapay"}

    start_date = str(request.query_params.get("start_date") or "").strip()
    end_date = str(request.query_params.get("end_date") or "").strip()
    date_filter: dict = {}
    if start_date:
        try:
            parsed_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            if len(start_date) <= 10:
                parsed_start = parsed_start.replace(hour=0, minute=0, second=0, microsecond=0)
            if parsed_start.tzinfo is None:
                parsed_start = parsed_start.replace(tzinfo=timezone.utc)
            date_filter["$gte"] = parsed_start.isoformat()
        except Exception:
            pass
    if end_date:
        try:
            parsed_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if len(end_date) <= 10:
                parsed_end = parsed_end.replace(hour=23, minute=59, second=59, microsecond=999999)
            if parsed_end.tzinfo is None:
                parsed_end = parsed_end.replace(tzinfo=timezone.utc)
            date_filter["$lte"] = parsed_end.isoformat()
        except Exception:
            pass

    history_query: dict = {"user_id": user.user_id}
    if date_filter:
        history_query["created_at"] = date_filter

    payments = (
        await db.payments.find(history_query, {"_id": 0})
        .sort("created_at", -1)
        .limit(50)
        .to_list(50)
    )
    transactions = (
        await db.payment_transactions.find(history_query, {"_id": 0})
        .sort("created_at", -1)
        .limit(50)
        .to_list(50)
    )

    serialized_payments = [_serialize_payment_history_row(row) for row in payments]
    serialized_transactions = [_serialize_payment_history_row(row) for row in transactions]

    if apply_gateway_filter:
        serialized_payments = [row for row in serialized_payments if row.get("gateway_key") == requested_gateway]
        serialized_transactions = [row for row in serialized_transactions if row.get("gateway_key") == requested_gateway]

    available_gateways = sorted(
        {
            row.get("gateway_key")
            for row in (serialized_payments + serialized_transactions)
            if row.get("gateway_key") in {"stripe", "paypal", "fedapay"}
        }
    )

    return {
        "payments": serialized_payments,
        "transactions": serialized_transactions,
        "gateway_filter": requested_gateway if apply_gateway_filter else "all",
        "available_gateways": available_gateways,
        "date_filter": {
            "start_date": start_date,
            "end_date": end_date,
        },
    }


@router.get("/payments/receipt-transparency-mode")
async def get_receipt_transparency_mode(request: Request):
    user = await _history_shared._get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"enabled": await _history_shared._get_receipt_transparency_mode(user.user_id)}


@router.post("/payments/receipt-transparency-mode")
async def set_receipt_transparency_mode(request: Request):
    user = await _history_shared._get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    enabled = bool(body.get("enabled", True))
    await db.user_preferences.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "receipt_transparency_mode": enabled,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"enabled": enabled, "status": "saved"}


# Split-module route aliases (compatibility exports)
download_tax_statement_csv = _tax_routes.download_tax_statement_csv
download_tax_statement_pdf = _tax_routes.download_tax_statement_pdf
tax_ready_csv_export = _tax_routes.tax_ready_csv_export

get_invoice = _document_routes.get_invoice
get_receipt = _document_routes.get_receipt
verify_document = _document_routes.verify_document
verify_export_integrity = _document_routes.verify_export_integrity
send_verified_receipt_email = _document_routes.send_verified_receipt_email
get_receipt_csv = _document_routes.get_receipt_csv
get_invoice_csv = _document_routes.get_invoice_csv
get_receipt_pdf = _document_routes.get_receipt_pdf
get_invoice_pdf = _document_routes.get_invoice_pdf
email_receipt = _document_routes.email_receipt
email_invoice = _document_routes.email_invoice

bulk_export_receipts = _bulk_routes.bulk_export_receipts
bulk_all_receipts = _bulk_routes.bulk_all_receipts
download_all_receipts_pdf_csv_bundle = _bulk_routes.download_all_receipts_pdf_csv_bundle
email_yearly_receipt_summary = _bulk_routes.email_yearly_receipt_summary

# Helper aliases required by existing imports/tests
configure_payment_history_routes = _history_shared.configure_payment_history_routes
_alert_missing_tax_fields = _history_shared._alert_missing_tax_fields
_build_single_document_csv_text = _history_shared._build_single_document_csv_text
_find_payment_record = _history_shared._find_payment_record
_format_payment_method_label = _history_shared._format_payment_method_label
_format_payment_status_label = _history_shared._format_payment_status_label
_generate_document_html = _history_shared._generate_document_html
_generate_pdf_from_payment = _history_shared._generate_pdf_from_payment
_get_receipt_transparency_mode = _history_shared._get_receipt_transparency_mode
_get_user_from_request = _history_shared._get_user_from_request
_missing_tax_fields = _history_shared._missing_tax_fields
_parse_statement_scope = _history_shared._parse_statement_scope
_payment_from_txn = _history_shared._payment_from_txn
_build_tax_statement_csv_text = _tax_routes._build_tax_statement_csv_text
_generate_tax_statement_pdf = _tax_routes._generate_tax_statement_pdf
_fetch_all_receipts_records_for_user = _bulk_routes._fetch_all_receipts_records_for_user
_generate_combined_receipts_single_pass = _bulk_routes._generate_combined_receipts_single_pass
