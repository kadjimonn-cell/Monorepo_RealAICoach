"""Receipt, invoice, verification, and delivery routes for payment history."""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hmac
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from utils.pdf_v15_filename import build_pdf_v15_filename

from .db import db
from .payments_history_shared import (
    BRAND_NAME,
    _apply_canonical_plan_pricing,
    _assert_plan_pricing_or_block,
    _build_integrity_payload,
    _build_single_document_csv_text,
    _find_payment_record,
    _format_payment_method_label,
    _generate_document_html,
    _generate_pdf_from_payment,
    _get_user_from_request,
    _send_payment_email,
    _safe_float,
    _sign_integrity_payload,
    _verify_document_lookup,
    _enforce_pdf_v15_enterprise,
)
from .payments_catalog import get_plan_name


router = APIRouter()


@router.get("/payments/invoice/{payment_id}")
async def get_invoice(payment_id: str, request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = await _find_payment_record(user.user_id, payment_id)
    plan_snapshot = await _assert_plan_pricing_or_block(payment, context="invoice_html")
    payment = _apply_canonical_plan_pricing(payment, plan_snapshot)
    token = request.query_params.get("token", "")
    pdf_url = f"/api/payments/invoice/{payment_id}/pdf?token={token}" if token else ""
    return HTMLResponse(content=_generate_document_html("invoice", payment, getattr(user, "name", ""), user.email, pdf_url=pdf_url))


@router.get("/payments/receipt/{payment_id}")
async def get_receipt(payment_id: str, request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = await _find_payment_record(user.user_id, payment_id)
    plan_snapshot = await _assert_plan_pricing_or_block(payment, context="receipt_html")
    payment = _apply_canonical_plan_pricing(payment, plan_snapshot)
    token = request.query_params.get("token", "")
    pdf_url = f"/api/payments/receipt/{payment_id}/pdf?token={token}" if token else ""
    return HTMLResponse(content=_generate_document_html("receipt", payment, getattr(user, "name", ""), user.email, pdf_url=pdf_url))


@router.get("/payments/verify")
async def verify_document(doc: str = "", t: str = ""):
    if not doc or not t:
        return {"verified": False, "reason": "Missing document reference or date."}
    payment, error = await _verify_document_lookup(doc)
    if not payment:
        return {"verified": False, "reason": error or "No matching document found in our records."}

    parts = doc.split("-")
    doc_type = parts[0]
    try:
        plan_snapshot = await _assert_plan_pricing_or_block(payment, context="verify_document")
        plan_name = plan_snapshot["plan_name"]
        display_amount = plan_snapshot["expected_amount"]
    except Exception:
        plan_name = await get_plan_name(payment.get("plan_id", ""))
        display_amount = payment.get("amount")
    return {"verified": True, "document_type": "Receipt" if doc_type == "RCT" else "Invoice", "document_number": doc, "date": t, "amount": display_amount, "plan": plan_name, "issuer": BRAND_NAME}


@router.get("/payments/export/verify")
async def verify_export_integrity(report_id: str = "", generated_at: str = "", row_count: int = 0, total_spent: float = 0, data_hash: str = "", signature: str = ""):
    if not report_id or not generated_at or not data_hash or not signature:
        return {"verified": False, "reason": "Missing required verification parameters."}
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except Exception:
        return {"verified": False, "reason": "Invalid generated_at format (expected ISO datetime)."}
    canonical_hash = data_hash.strip().lower()
    payload = _build_integrity_payload(report_id.strip(), generated_at.strip(), row_count, total_spent, canonical_hash)
    expected = _sign_integrity_payload(payload)
    if not expected:
        return {"verified": False, "reason": "Verification secret is not configured."}
    ok = hmac.compare_digest(expected, signature.strip().lower())
    return {"verified": ok, "report_id": report_id, "generated_at": generated_at, "row_count": row_count, "total_spent": round(float(total_spent), 2), "data_hash": canonical_hash, "reason": "Signature verified" if ok else "Signature mismatch"}


@router.post("/payments/verify/send-email")
async def send_verified_receipt_email(request: Request):
    from utils.email_service import is_email_configured, send_catalog_template

    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Email service not configured.")
    body = await request.json()
    doc = body.get("doc", "")
    t = body.get("t", "")
    payment_id = body.get("payment_id", "")
    doc_type = (body.get("doc_type", "receipt") or "receipt").lower()
    recipient = body.get("email", "").strip().lower()
    if not recipient or "@" not in recipient:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if (not doc or not t) and payment_id:
        p = await db.payments.find_one({"payment_id": payment_id}, {"_id": 0, "payment_id": 1, "created_at": 1})
        if not p:
            raise HTTPException(status_code=404, detail="Payment not found for provided payment_id.")
        created = p.get("created_at")
        try:
            created_dt = created if isinstance(created, datetime) else datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except Exception:
            created_dt = datetime.now(timezone.utc)
        prefix = "RCT" if doc_type != "invoice" else "INV"
        doc = f"{prefix}-{created_dt.strftime('%Y%m%d')}-{str(payment_id)[:8].upper()}"
        t = created_dt.strftime("%b %d, %Y")
    if not doc or not t:
        raise HTTPException(status_code=400, detail="Missing document reference.")
    payment, error = await _verify_document_lookup(doc)
    if not payment:
        raise HTTPException(status_code=404, detail=error or "Document not found in our records.")
    plan_snapshot = await _assert_plan_pricing_or_block(payment, context="verify_send_email")
    payment = _apply_canonical_plan_pricing(payment, plan_snapshot)
    doc_type_prefix = doc.split("-")[0]
    doc_type_label = "Receipt" if doc_type_prefix == "RCT" else "Invoice"
    pdf_doc_type = "invoice" if doc_type_prefix == "INV" else "receipt"
    amount = plan_snapshot["expected_amount"]
    plan_name = plan_snapshot["plan_name"]
    os.environ.get("FRONTEND_BASE_URL", "")
    user_doc = None
    user_id = str(payment.get("user_id") or "").strip()
    if user_id:
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "email": 1})
    pdf_user_name = (user_doc or {}).get("name", "")
    pdf_user_email = (user_doc or {}).get("email") or payment.get("email") or recipient
    pdf_bytes = await _generate_pdf_from_payment(pdf_doc_type, payment, pdf_user_name, pdf_user_email)
    attachment = {"filename": build_pdf_v15_filename(pdf_doc_type, payment.get("payment_id") or doc), "content": base64.b64encode(pdf_bytes).decode("utf-8"), "content_type": "application/pdf"}
    await send_catalog_template(recipient_email=recipient, template_key="invoice_document", invoice_number=doc, amount=f"${amount:.2f}" if isinstance(amount, (int, float)) else str(amount), period=plan_snapshot["billing_period"].title(), plan_name=plan_name, attachments=[attachment])
    return {"ok": True, "message": f"{doc_type_label} sent to {recipient}"}


@router.get("/payments/receipt/{payment_id}/csv")
async def get_receipt_csv(payment_id: str, request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = await _find_payment_record(user.user_id, payment_id)
    csv_content = _build_single_document_csv_text("receipt", payment, getattr(user, "name", ""), user.email)
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="receipt_{str(payment_id)[:8]}_enterprise.csv"', "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@router.get("/payments/invoice/{payment_id}/csv")
async def get_invoice_csv(payment_id: str, request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = await _find_payment_record(user.user_id, payment_id)
    csv_content = _build_single_document_csv_text("invoice", payment, getattr(user, "name", ""), user.email)
    return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="invoice_{str(payment_id)[:8]}_enterprise.csv"', "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


def _document_transparency_override(request: Request, payment: dict) -> dict:
    if (request.query_params.get("tm") or request.query_params.get("transparency") or "").lower() in {"0", "false", "off"}:
        payment["transparency_mode"] = False
    return payment


@router.get("/payments/receipt/{payment_id}/pdf")
async def get_receipt_pdf(payment_id: str, request: Request, inline: str = None):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = _document_transparency_override(request, await _apply_and_load_payment(user.user_id, payment_id, "receipt_pdf"))
    pdf_bytes = _enforce_pdf_v15_enterprise(await _generate_pdf_from_payment("receipt", payment, getattr(user, "name", ""), user.email), f"receipt_{payment_id}")
    disposition = "inline" if inline else f'attachment; filename="{build_pdf_v15_filename("receipt", payment_id)}"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": disposition, "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@router.get("/payments/invoice/{payment_id}/pdf")
async def get_invoice_pdf(payment_id: str, request: Request, inline: str = None):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = _document_transparency_override(request, await _apply_and_load_payment(user.user_id, payment_id, "invoice_pdf"))
    pdf_bytes = _enforce_pdf_v15_enterprise(await _generate_pdf_from_payment("invoice", payment, getattr(user, "name", ""), user.email), f"invoice_{payment_id}")
    disposition = "inline" if inline else f'attachment; filename="{build_pdf_v15_filename("invoice", payment_id)}"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": disposition, "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


async def _apply_and_load_payment(user_id: str, payment_id: str, context: str) -> dict:
    payment = await _find_payment_record(user_id, payment_id)
    plan_snapshot = await _assert_plan_pricing_or_block(payment, context=context)
    return _apply_canonical_plan_pricing(payment, plan_snapshot)


@router.post("/payments/email-receipt/{payment_id}")
async def email_receipt(payment_id: str, request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payment = await _apply_and_load_payment(user.user_id, payment_id, "email_receipt")
    plan_snapshot = await _assert_plan_pricing_or_block(payment, context="email_receipt_number")
    created_at = str(payment.get("created_at") or datetime.now(timezone.utc).isoformat())
    pid = payment.get("payment_id") or payment.get("id", "N/A")
    receipt_number = f"RCT-{created_at[:10].replace('-', '')}-{str(pid)[:8].upper()}" if pid != "N/A" else "RCT-UNKNOWN"
    await _send_payment_email(user.email, getattr(user, "name", "") or "", plan_snapshot["plan_name"], plan_snapshot["expected_amount"], _format_payment_method_label(payment.get("payment_method", "card")), receipt_number, plan_snapshot["billing_period"], datetime.now(timezone.utc).strftime("%b %d, %Y"), amount_local=_safe_float(payment.get("total_amount", plan_snapshot["expected_amount"]), plan_snapshot["expected_amount"]), currency=str(payment.get("currency", "USD")).upper(), transaction_context=payment, send_admin_alert=False)
    return {"status": "sent", "email": user.email}


@router.post("/payments/email-invoice/{payment_id}")
async def email_invoice(payment_id: str, request: Request):
    from utils.email_service import send_catalog_template

    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        body = await request.json()
    except Exception:
        body = {}
    recipient = body.get("email") or user.email
    payment = await _apply_and_load_payment(user.user_id, payment_id, "email_invoice")
    plan_snapshot = await _assert_plan_pricing_or_block(payment, context="email_invoice_pdf")
    payment.get("created_at", "")
    pid = payment.get("payment_id") or payment.get("id", "N/A")
    invoice_pdf = await _generate_pdf_from_payment("invoice", payment, getattr(user, "name", "") or "", user.email)
    invoice_attachment = {"filename": build_pdf_v15_filename("invoice", pid), "content": base64.b64encode(invoice_pdf).decode("utf-8"), "content_type": "application/pdf"}
    result = await send_catalog_template(recipient_email=recipient, template_key="invoice_document", invoice_number=str(pid), amount=f"${plan_snapshot['expected_amount']:.2f}", period=plan_snapshot["billing_period"].title(), plan_name=plan_snapshot["plan_name"], attachments=[invoice_attachment])
    if result.get("success"):
        return {"status": "sent", "email": recipient}
    raise HTTPException(status_code=500, detail="Failed to send email")
