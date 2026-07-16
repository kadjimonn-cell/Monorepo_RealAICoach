"""Bulk receipt export routes for payment history."""

from __future__ import annotations

from datetime import datetime, timezone
import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from utils.pdf_v15_filename import build_pdf_v15_filename

from .db import db
from .payments_reporting_routes import _build_payment_history_csv_text, _fetch_payment_history_export_items
from .payments_history_shared import (
    _enforce_pdf_v15_enterprise,
    _format_payment_method_label,
    _format_payment_status_label,
    _generate_pdf_from_payment,
    _get_user_from_request,
    _parse_created_at,
)


router = APIRouter()


async def _fetch_all_receipts_records_for_user(user, start_date: str = "", end_date: str = "") -> list[dict]:
    date_filter: dict = {}
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            date_filter["$gte"] = sd.isoformat()
        except Exception:
            pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            ed = ed.replace(hour=23, minute=59, second=59)
            date_filter["$lte"] = ed.isoformat()
        except Exception:
            pass
    query: dict = {"user_id": user.user_id}
    if date_filter:
        query["created_at"] = date_filter
    payments_list = await db.payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=500)
    txn_list = await db.payment_transactions.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=500)
    all_payments: list[dict] = []
    seen_ids: set[str] = set()
    for p in payments_list:
        pid = p.get("payment_id") or p.get("id", "")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            all_payments.append(p)
    for t in txn_list:
        pid = t.get("payment_id") or t.get("session_id") or t.get("id", "")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            all_payments.append({"id": t.get("id") or pid, "payment_id": pid, "plan_id": t.get("plan_id"), "amount": t.get("amount"), "currency": t.get("currency"), "payment_method": t.get("payment_method"), "status": t.get("payment_status") or t.get("status") or "completed", "billing_period": t.get("billing_period"), "created_at": t.get("created_at")})
    return all_payments


@router.post("/payments/bulk-export")
async def bulk_export_receipts(request: Request):
    import zipfile

    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    payment_ids = body.get("payment_ids", [])
    doc_type = body.get("doc_type", "receipt")
    if not payment_ids or not isinstance(payment_ids, list):
        raise HTTPException(status_code=400, detail="Provide a list of payment_ids.")
    if len(payment_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 payments per export.")
    if doc_type not in ("receipt", "invoice"):
        doc_type = "receipt"
    zip_buffer = io.BytesIO()
    included = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for pid in payment_ids:
            payment = await db.payments.find_one({"user_id": user.user_id, "$or": [{"id": pid}, {"payment_id": pid}]}, {"_id": 0})
            if not payment:
                txn = await db.payment_transactions.find_one(
                    {
                        "user_id": user.user_id,
                        "$or": [
                            {"payment_id": pid},
                            {"session_id": pid},
                            {"id": pid},
                            {"transaction_id": pid},
                        ],
                    },
                    {"_id": 0},
                )
                if txn:
                    payment = {"id": txn.get("id") or pid, "payment_id": txn.get("payment_id") or pid, "plan_id": txn.get("plan_id"), "amount": txn.get("amount"), "currency": txn.get("currency"), "payment_method": txn.get("payment_method"), "status": txn.get("payment_status") or txn.get("status") or "completed", "billing_period": txn.get("billing_period"), "created_at": txn.get("created_at")}
            if not payment:
                continue
            try:
                pdf_bytes = _generate_pdf_from_payment(doc_type, payment, getattr(user, "name", ""), user.email)
                short_id = str(pid).replace("/", "_").replace("\\", "_")[:16]
                zf.writestr(build_pdf_v15_filename(doc_type, f"{short_id}-{included + 1}"), pdf_bytes)
                included += 1
            except Exception:
                continue
    if included == 0:
        raise HTTPException(status_code=404, detail="No valid payments found for export.")
    zip_buffer.seek(0)
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{doc_type}s_export.zip"', "X-Included-Count": str(included)})


@router.get("/payments/receipts/bulk-all")
async def bulk_all_receipts(request: Request, format: str = "combined", start_date: str = "", end_date: str = "", token: str = ""):
    import zipfile

    user = await _get_user_from_request(request)
    if not user and token:
        from .db import verify_token
        try:
            user = await verify_token(token)
        except Exception:
            user = None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    all_payments = await _fetch_all_receipts_records_for_user(user, start_date=start_date, end_date=end_date)
    if not all_payments:
        raise HTTPException(status_code=404, detail="No receipts found for the selected period.")
    user_name = getattr(user, "name", "") or ""
    user_email = user.email or ""
    export_format = format.lower().strip()
    if export_format == "combined":
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            return await _generate_combined_receipts_single_pass(all_payments, user_name, user_email, start_date, end_date)
        writer = PdfWriter()
        for payment in all_payments:
            try:
                reader = PdfReader(io.BytesIO(_generate_pdf_from_payment("receipt", payment, user_name, user_email)))
                for page in reader.pages:
                    writer.add_page(page)
            except Exception:
                continue
        if len(writer.pages) == 0:
            raise HTTPException(status_code=404, detail="No valid receipts could be generated.")
        output = io.BytesIO()
        writer.write(output)
        merged_pdf_bytes = _enforce_pdf_v15_enterprise(output.getvalue(), f"receipts_bulk_combined_{user.user_id}")
        date_suffix = (f"_from_{start_date}" if start_date else "") + (f"_to_{end_date}" if end_date else "")
        return Response(content=merged_pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("receipts-bulk", f"{user.user_id}{date_suffix}")}"', "X-Included-Count": str(len(writer.pages)), "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})
    zip_buffer = io.BytesIO()
    included = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for payment in all_payments:
            try:
                pdf_bytes = _enforce_pdf_v15_enterprise(_generate_pdf_from_payment("receipt", payment, user_name, user_email), f"receipt_zip_{payment.get('payment_id') or payment.get('id', 'unknown')}")
                pid = payment.get("payment_id") or payment.get("id", "unknown")
                short_id = str(pid).replace("/", "_").replace("\\", "_")[:16]
                zf.writestr(build_pdf_v15_filename("receipt", f"{short_id}-{included + 1}"), pdf_bytes)
                included += 1
            except Exception:
                continue
    if included == 0:
        raise HTTPException(status_code=404, detail="No valid receipts could be generated.")
    zip_buffer.seek(0)
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="rac-receipts-bundle-v15-{str(user.user_id).lower()}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.zip"', "X-Included-Count": str(included)})


@router.get("/payments/receipts/download-all-bundle")
async def download_all_receipts_pdf_csv_bundle(request: Request, start_date: str = "", end_date: str = "", token: str = ""):
    import zipfile

    user = await _get_user_from_request(request)
    if not user and token:
        from .db import verify_token
        try:
            user = await verify_token(token)
        except Exception:
            user = None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    all_payments = await _fetch_all_receipts_records_for_user(user, start_date=start_date, end_date=end_date)
    if not all_payments:
        raise HTTPException(status_code=404, detail="No receipts found for the selected period.")
    combined_response = await _generate_combined_receipts_single_pass(all_payments, getattr(user, "name", "") or "", user.email or "", start_date=start_date, end_date=end_date)
    pdf_bytes = combined_response.body
    included_count = combined_response.headers.get("X-Included-Count", str(len(all_payments)))
    export_items = await _fetch_payment_history_export_items(user.user_id, limit=5000)
    start_dt = _parse_created_at(start_date) if start_date else None
    end_dt = _parse_created_at(end_date) if end_date else None
    if end_dt:
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
    if start_dt or end_dt:
        filtered_items: list[dict] = []
        for item in export_items:
            item_dt = _parse_created_at(item.get("created_at"))
            if not item_dt:
                continue
            if start_dt and item_dt < start_dt:
                continue
            if end_dt and item_dt > end_dt:
                continue
            filtered_items.append(item)
        export_items = filtered_items
    csv_content = _build_payment_history_csv_text(export_items)
    date_suffix = (f"_from_{start_date}" if start_date else "") + (f"_to_{end_date}" if end_date else "")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(build_pdf_v15_filename("receipts-bulk", f"{user.user_id}{date_suffix}"), pdf_bytes)
        zf.writestr(f"rac-payments-export-v15-{date_suffix.strip('_') or datetime.now(timezone.utc).strftime('%Y%m%d')}.csv", csv_content)
    zip_buffer.seek(0)
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="rac-receipts-csv-bundle-v15-{str(user.user_id).lower()}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.zip"', "X-Included-Count": str(included_count), "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


async def _generate_combined_receipts_single_pass(all_payments: list, user_name: str, user_email: str, start_date: str = "", end_date: str = "") -> Response:
    from fpdf import FPDF

    plan_names = {"basic": "Basic", "premium": "Premium", "free": "Free"}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    included = 0
    for payment in all_payments:
        try:
            plan_name = plan_names.get(payment.get("plan_id", ""), payment.get("plan_id", "Unknown"))
            amount = payment.get("amount", 0)
            method_display = _format_payment_method_label(payment.get("payment_method", "card"))
            status_display = _format_payment_status_label(payment.get("status", "completed"))
            created = payment.get("created_at", "")
            payment_id = payment.get("payment_id", payment.get("id", "N/A"))
            billing = payment.get("billing_period", "monthly")
            try:
                d = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
                date_str = d.strftime("%B %d, %Y")
            except Exception:
                date_str = str(created)[:10]
            doc_num = f"RCT-{str(created)[:10].replace('-', '')}-{payment_id[:8].upper()}" if payment_id != "N/A" else f"RCT-{str(created)[:10].replace('-', '')}"
            pdf.add_page()
            pw = pdf.w - 40
            pdf.set_fill_color(14, 165, 233)
            pdf.rect(0, 0, 210, 44, "F")
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 20)
            pdf.set_xy(20, 10)
            pdf.cell(0, 10, "RECEIPT", ln=True)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_xy(20, 22)
            pdf.cell(0, 5, f"{doc_num}  |  {date_str}", ln=True)
            pdf.set_y(52)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(100, 116, 139)
            pdf.set_x(20)
            pdf.cell(0, 6, "BILL TO", ln=True)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(30, 41, 59)
            pdf.set_x(20)
            pdf.cell(0, 6, user_name or "Customer", ln=True)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(100, 116, 139)
            pdf.set_x(20)
            pdf.cell(0, 5, user_email, ln=True)
            pdf.ln(10)
            pdf.set_fill_color(241, 245, 249)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(51, 65, 85)
            pdf.set_x(20)
            pdf.cell(pw * 0.5, 8, "  Description", border="B", fill=True)
            pdf.cell(pw * 0.2, 8, "Period", border="B", fill=True, align="C")
            pdf.cell(pw * 0.3, 8, "Amount", border="B", fill=True, align="R")
            pdf.ln()
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(30, 41, 59)
            pdf.set_x(20)
            pdf.cell(pw * 0.5, 10, f"  {plan_name} Plan Subscription", border="B")
            pdf.cell(pw * 0.2, 10, billing.title(), border="B", align="C")
            pdf.cell(pw * 0.3, 10, f"${amount:,.2f}", border="B", align="R")
            pdf.ln(12)
            for label, value in [("Method", method_display), ("Status", status_display), ("Transaction ID", str(payment_id)), ("Date", date_str)]:
                pdf.set_text_color(100, 116, 139)
                pdf.set_x(20)
                pdf.cell(pw * 0.35, 6, label)
                pdf.set_text_color(30, 41, 59)
                pdf.cell(pw * 0.65, 6, value, ln=True)
            included += 1
        except Exception:
            continue
    if included == 0:
        raise HTTPException(status_code=404, detail="No valid receipts could be generated.")
    date_suffix = (f"_from_{start_date}" if start_date else "") + (f"_to_{end_date}" if end_date else "")
    single_pass_pdf = _enforce_pdf_v15_enterprise(bytes(pdf.output()), f"receipts_single_pass_{user_email}")
    return Response(content=single_pass_pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("all-receipts", f"{user_email}{date_suffix}")}"', "X-Included-Count": str(included), "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@router.post("/payments/receipts/email-yearly-summary")
async def email_yearly_receipt_summary(request: Request):
    import base64
    from utils.email_service import send_email
    from utils.email_templates import TEMPLATE_CATALOG

    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    year = int(body.get("year", datetime.now().year - 1))
    all_payments = await _fetch_all_receipts_records_for_user(user, start_date=f"{year}-01-01", end_date=f"{year}-12-31")
    if not all_payments:
        raise HTTPException(status_code=404, detail=f"No receipts found for {year}.")
    user_name = getattr(user, "name", "") or ""
    user_email = user.email or ""
    try:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for payment in all_payments:
            try:
                reader = PdfReader(io.BytesIO(_generate_pdf_from_payment("receipt", payment, user_name, user_email)))
                for page in reader.pages:
                    writer.add_page(page)
            except Exception:
                continue
        output = io.BytesIO()
        writer.write(output)
        pdf_bytes = _enforce_pdf_v15_enterprise(output.getvalue(), f"annual_receipts_{year}")
    except ImportError:
        pdf_bytes = (await _generate_combined_receipts_single_pass(all_payments, user_name, user_email, f"{year}-01-01", f"{year}-12-31")).body
    total_amount = sum(float(p.get("amount", 0) or 0) for p in all_payments)
    tpl = TEMPLATE_CATALOG["annual_receipt_summary"]["builder"](user_name=getattr(user, "name", ""), year=str(year), total_amount=f"${total_amount:,.2f}", receipt_count=len(all_payments))
    attachment = {"filename": build_pdf_v15_filename("annual-receipts", year), "content": base64.b64encode(pdf_bytes).decode("utf-8"), "content_type": "application/pdf"}
    result = await send_email(recipient_email=user_email, subject=tpl.subject, content=tpl.html, template_key="annual_receipt_summary", attachments=[attachment])
    if result.get("success"):
        return {"status": "sent", "year": year, "receipts_count": len(all_payments), "total_amount": round(total_amount, 2), "email": user_email}
    raise HTTPException(status_code=500, detail=result.get("error", "Failed to send email"))
