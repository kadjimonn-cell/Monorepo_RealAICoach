"""Tax statement and tax export routes for payment history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from utils.pdf_v15_filename import build_pdf_v15_filename

from .db import db
from .payments_history_shared import (
    _get_user_from_request,
    _parse_statement_scope,
    _receipt_product_type_label,
    _safe_float,
    _enforce_pdf_v15_enterprise,
)


router = APIRouter()


def _build_tax_statement_csv_text(*, rows: list[Dict[str, Any]], user_name: str, user_email: str, scope: str, period_label: str) -> str:
    import csv
    import io

    subtotal_total = sum(_safe_float(r.get("subtotal", 0), 0.0) for r in rows)
    tax_total = sum(_safe_float(r.get("tax_amount", 0), 0.0) for r in rows)
    fee_total = sum(_safe_float(r.get("processing_fee", 0), 0.0) for r in rows)
    customer_charge_total = sum(_safe_float(r.get("total_amount", r.get("amount_gross", 0)), 0.0) for r in rows)
    net_total = sum(_safe_float(r.get("amount_net", 0), 0.0) for r in rows)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Tax Statement", period_label, scope.title()])
    writer.writerow(["User", user_name])
    writer.writerow(["Email", user_email])
    writer.writerow([])
    writer.writerow(["Base Subscription Price Total", f"{subtotal_total:.2f}"])
    writer.writerow(["Applicable Tax Total", f"{tax_total:.2f}"])
    writer.writerow(["Provider Processing Fee Total", f"{fee_total:.2f}"])
    writer.writerow(["Customer Charge Total", f"{customer_charge_total:.2f}"])
    writer.writerow(["Net Settlement After Fee Total", f"{net_total:.2f}"])
    writer.writerow([])
    writer.writerow([
        "Timestamp", "Transaction ID", "Provider", "Plan", "Currency", "Base Subscription Price", "Applicable Tax",
        "Tax Rate", "Jurisdiction", "Product Type", "Provider Processing Fee", "Customer Charge Total", "Net Settlement After Fee", "Status",
    ])
    for row in rows:
        jurisdiction = row.get("jurisdiction", {}) if isinstance(row.get("jurisdiction"), dict) else {}
        jurisdiction_label = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-")
        writer.writerow([
            row.get("created_at", ""),
            row.get("transaction_id") or row.get("payment_id") or row.get("session_id") or "",
            row.get("provider") or row.get("gateway") or row.get("payment_method") or "",
            row.get("plan_id", ""),
            row.get("currency", "USD"),
            f"{_safe_float(row.get('subtotal', 0), 0.0):.2f}",
            f"{_safe_float(row.get('tax_amount', 0), 0.0):.2f}",
            f"{_safe_float(row.get('tax_rate', 0), 0.0):.6f}",
            jurisdiction_label,
            _receipt_product_type_label(row.get("product_type", "education_digital_service")),
            f"{_safe_float(row.get('processing_fee', 0), 0.0):.2f}",
            f"{_safe_float(row.get('total_amount', row.get('amount_gross', 0)), 0.0):.2f}",
            f"{_safe_float(row.get('amount_net', 0), 0.0):.2f}",
            row.get("status") or row.get("payment_status") or "",
        ])
    out = buffer.getvalue()
    buffer.close()
    return out


def _generate_tax_statement_pdf(*, rows: list[Dict[str, Any]], user_name: str, user_email: str, scope: str, period_label: str) -> bytes:
    from fpdf import FPDF

    subtotal_total = sum(_safe_float(r.get("subtotal", 0), 0.0) for r in rows)
    tax_total = sum(_safe_float(r.get("tax_amount", 0), 0.0) for r in rows)
    fee_total = sum(_safe_float(r.get("processing_fee", 0), 0.0) for r in rows)
    customer_charge_total = sum(_safe_float(r.get("total_amount", r.get("amount_gross", 0)), 0.0) for r in rows)
    net_total = sum(_safe_float(r.get("amount_net", 0), 0.0) for r in rows)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"RealAICoach Tax Statement ({scope.title()})", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 7, f"Period: {period_label}", ln=True)
    pdf.cell(0, 7, f"User: {user_name} ({user_email})", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(40, 7, "Base Price")
    pdf.cell(30, 7, f"{subtotal_total:.2f}")
    pdf.cell(30, 7, "Tax")
    pdf.cell(30, 7, f"{tax_total:.2f}", ln=True)
    pdf.cell(40, 7, "Provider Fee")
    pdf.cell(30, 7, f"{fee_total:.2f}")
    pdf.cell(30, 7, "Customer Total")
    pdf.cell(30, 7, f"{customer_charge_total:.2f}", ln=True)
    pdf.cell(40, 7, "Net Settlement")
    pdf.cell(30, 7, f"{net_total:.2f}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(38, 7, "Date", border=1)
    pdf.cell(28, 7, "Provider", border=1)
    pdf.cell(22, 7, "Currency", border=1)
    pdf.cell(22, 7, "Tax", border=1)
    pdf.cell(22, 7, "Cust Total", border=1)
    pdf.cell(22, 7, "Net", border=1)
    pdf.cell(36, 7, "Jurisdiction", border=1, ln=True)
    pdf.set_font("Arial", "", 9)
    for row in rows[:180]:
        jurisdiction = row.get("jurisdiction", {}) if isinstance(row.get("jurisdiction"), dict) else {}
        jurisdiction_label = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-")[:18]
        created_at = str(row.get("created_at", ""))[:10]
        provider = str(row.get("provider") or row.get("gateway") or row.get("payment_method") or "")[:14]
        currency = str(row.get("currency", "USD"))[:8]
        tax_val = f"{_safe_float(row.get('tax_amount', 0), 0.0):.2f}"
        gross_val = f"{_safe_float(row.get('total_amount', row.get('amount_gross', 0)), 0.0):.2f}"
        net_val = f"{_safe_float(row.get('amount_net', 0), 0.0):.2f}"
        pdf.cell(38, 6, created_at, border=1)
        pdf.cell(28, 6, provider, border=1)
        pdf.cell(22, 6, currency, border=1)
        pdf.cell(22, 6, tax_val, border=1)
        pdf.cell(22, 6, gross_val, border=1)
        pdf.cell(22, 6, net_val, border=1)
        pdf.cell(36, 6, jurisdiction_label, border=1, ln=True)
    return _enforce_pdf_v15_enterprise(bytes(pdf.output(dest="S")), f"tax_statement_{scope}_{period_label}")


@router.get("/payments/tax-statement/csv")
async def download_tax_statement_csv(
    request: Request,
    scope: str = Query("monthly"),
    year: int = Query(default_factory=lambda: datetime.now(timezone.utc).year),
    month: Optional[int] = Query(None),
):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    prefix, label = _parse_statement_scope(scope, year, month)
    rows = await db.payment_transactions.find({"user_id": user.user_id, "created_at": {"$regex": f"^{prefix}"}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    csv_content = _build_tax_statement_csv_text(rows=rows, user_name=getattr(user, "name", "") or "", user_email=user.email, scope=scope, period_label=label)
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="tax_statement_{scope}_{label}.csv"', "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@router.get("/payments/tax-statement/pdf")
async def download_tax_statement_pdf(
    request: Request,
    scope: str = Query("monthly"),
    year: int = Query(default_factory=lambda: datetime.now(timezone.utc).year),
    month: Optional[int] = Query(None),
):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    prefix, label = _parse_statement_scope(scope, year, month)
    rows = await db.payment_transactions.find({"user_id": user.user_id, "created_at": {"$regex": f"^{prefix}"}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    pdf_bytes = _generate_tax_statement_pdf(rows=rows, user_name=getattr(user, "name", "") or "", user_email=user.email, scope=scope, period_label=label)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("tax-statement", f"{scope}-{label}")}"', "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@router.get("/payments/tax-export")
async def tax_ready_csv_export(request: Request):
    import csv
    import io

    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    is_admin = getattr(user, "is_admin", False)
    query: dict = {} if is_admin else {"user_id": user.user_id}
    payments = await db.payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)
    transactions = await db.payment_transactions.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)
    user_ids = list({p.get("user_id") for p in payments} | {t.get("user_id") for t in transactions})
    user_docs = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(len(user_ids))
    user_map = {u["user_id"]: u for u in user_docs}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Record Type", "Document ID", "Payment ID", "Transaction ID", "User ID", "Payer Email", "Payer Name", "Plan", "Billing Period", "Currency", "Base Subscription Price", "Applicable Tax", "Tax Rate", "Tax Jurisdiction", "Product Type", "Provider Processing Fee", "Customer Charge Total", "Net Settlement After Fee", "Payment Method", "Gateway", "Status", "Description"])
    for source, record_type, status_key, gateway_key in ((payments, "payment", "status", "gateway"), (transactions, "transaction", "payment_status", "provider")):
        for row in source:
            if record_type == "transaction" and row.get("transaction_id") in {p.get("payment_id") for p in payments}:
                continue
            u = user_map.get(row.get("user_id"), {})
            created = row.get("created_at", "")
            if hasattr(created, "isoformat"):
                created = created.isoformat()
            amount_val = float(row.get("amount", 0) or 0)
            tax_val = float(row.get("tax_amount", 0) or 0)
            fee_val = float(row.get("processing_fee", row.get("fee", 0)) or 0)
            subtotal_val = float(row.get("subtotal", amount_val) or amount_val)
            gross_val = float(row.get("amount_gross", subtotal_val + tax_val) or (subtotal_val + tax_val))
            total_val = float(row.get("total_amount", gross_val) or gross_val)
            net_val = float(row.get("amount_net", max(total_val - fee_val, 0)) or max(total_val - fee_val, 0))
            jurisdiction = row.get("jurisdiction", {}) if isinstance(row.get("jurisdiction"), dict) else {}
            jurisdiction_label = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-")
            payment_id = row.get("payment_id", row.get("id", ""))
            tx_id = row.get("transaction_id", payment_id)
            doc_id = f"RCT-{str(created)[:10].replace('-', '')}-{str(tx_id if record_type == 'transaction' else payment_id).upper()[:8]}"
            writer.writerow([
                str(created)[:19], record_type, doc_id, payment_id, tx_id, row.get("user_id", ""), u.get("email", row.get("user_id", "")), u.get("name", ""),
                row.get("plan", row.get("subscription_plan", row.get("plan_id", row.get("type", "")))), row.get("billing_period", ""), row.get("currency", "USD"),
                f"{subtotal_val:.2f}", f"{tax_val:.2f}", f"{float(row.get('tax_rate', 0) or 0):.6f}", jurisdiction_label,
                _receipt_product_type_label(row.get("product_type", "education_digital_service")), f"{fee_val:.2f}", f"{total_val:.2f}", f"{net_val:.2f}",
                row.get("payment_method", ""), row.get(gateway_key, row.get("payment_method", "")), row.get(status_key, row.get("status", "")), row.get("description", f"{record_type.title()} - {row.get('type', row.get('plan_id', 'N/A'))}"),
            ])
    output.seek(0)
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scope = "platform" if is_admin else "personal"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=tax_export_{scope}_{now}.csv"})
