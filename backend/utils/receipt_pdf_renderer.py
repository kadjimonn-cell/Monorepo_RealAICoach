"""Split-out PDF renderer for payment receipts and invoices."""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from datetime import datetime

from utils.pdf_v15_export import enforce_pdf_v15_enterprise


def generate_pdf_from_payment(doc_type: str, payment: dict, user_name: str, user_email: str, branding_override: dict | None = None) -> bytes:
    from fpdf import FPDF
    from urllib.parse import urlencode
    from utils.receipt_generator import (
        _load_branding_from_db_sync as _load_branding,
        _logger as _log,
    )
    try:
        from services.receipt_pdf_pro import generate_receipt_pdf_pro
        _branding = branding_override or _load_branding()
        pro_bytes = generate_receipt_pdf_pro(doc_type, payment, user_name, user_email, _branding)
        return enforce_pdf_v15_enterprise(pro_bytes, f"receipt_pro_{doc_type}_{payment.get('payment_id', payment.get('id', 'na'))}")
    except Exception as exc:
        _log.warning(f"Receipt PDF pro renderer fallback to legacy: {exc}")

    from utils.receipt_generator import (
        BRAND,
        SITE_URL,
        FRONTEND_BASE_URL,
        RECEIPT_VERSION,
        _V7_STRIPE_COLORS,
        _L,
        _detect_locale,
        _display_product_type,
        _get_document_logo_temp_path,
        _hex_to_rgb,
        _is_french_payment,
        _load_branding_from_db_sync,
        format_payment_method_label,
        format_payment_status_label,
        _logger,
    )

    branding = branding_override or _load_branding_from_db_sync()
    brand_display = branding.get("brand_name", BRAND)
    primary_hex = branding.get("primary_color", "#2563EB")
    footer_text = branding.get("footer_text", "Thank you for your business!")
    company_info = branding.get("company_info", "support@realaicoach.app")
    show_qr = branding.get("show_qr_code", True)

    plan_names = {"basic": "Basic", "premium": "Premium", "free": "Free"}
    plan_name = plan_names.get(payment.get("plan_id", ""), payment.get("plan_id", "Unknown"))
    amount = float(payment.get("amount", 0) or 0)
    status = payment.get("status", "completed")
    created = payment.get("created_at", "")
    payment_id = payment.get("payment_id", payment.get("id", "N/A"))
    billing = payment.get("billing_period", "monthly")
    is_fr = _is_french_payment(payment)
    lang = _detect_locale(payment)

    try:
        d = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
        date_str = d.strftime("%B %d, %Y")
        date_short = d.strftime("%Y-%m-%d")
    except Exception:
        date_str = str(created)[:10]
        date_short = str(created)[:10]

    doc_prefix = "INV" if doc_type == "invoice" else "RCT"
    doc_num = f"{doc_prefix}-{date_short.replace('-', '')}-{payment_id[:8].upper()}" if payment_id != "N/A" else f"{doc_prefix}-{date_short.replace('-', '')}"
    title = "FACTURE" if (doc_type == "invoice" and is_fr) else "REÇU" if (doc_type == "receipt" and is_fr) else "INVOICE" if doc_type == "invoice" else "RECEIPT"
    method_display = format_payment_method_label(payment.get("payment_method", "card"))
    status_display = format_payment_status_label(status)
    if is_fr:
        status_display = "Payé" if status_display.lower() in {"paid", "completed", "success"} else "En attente" if status_display.lower() in {"pending", "initiated"} else status_display
    is_paid = status_display.lower() in {"paid", "completed", "success"}

    try:
        currency = str(payment.get("currency", "USD") or "USD").upper()
        subtotal = float(payment.get("subtotal", amount) or amount)
        tax_amount = float(payment.get("tax_amount", 0) or 0)
        fee_amount = float(payment.get("processing_fee", payment.get("fee", 0)) or 0)
        gross_amount = float(payment.get("amount_gross", subtotal + tax_amount) or (subtotal + tax_amount))
        total_amount = float(payment.get("total_amount", gross_amount) or gross_amount)
        jurisdiction = payment.get("jurisdiction", {}) if isinstance(payment.get("jurisdiction"), dict) else {}
        tax_jurisdiction = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-") or "N/A"
        tax_rate = float(payment.get("tax_rate", 0) or 0)
        transaction_id = str(payment.get("transaction_id") or payment.get("id") or payment.get("payment_id") or "N/A")
        secret = os.environ.get("PAYMENT_EXPORT_SIGNATURE_SECRET") or os.environ.get("JWT_SECRET") or ""
        sig_payload = f"{doc_num}|{transaction_id}|{user_email}|{total_amount:.2f}|{currency}|{date_short}|{status_display}"
        verify_hash = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()
        verify_signature = hmac.new(secret.encode("utf-8"), sig_payload.encode("utf-8"), hashlib.sha256).hexdigest() if secret else ""
        verify_api_url = f"{FRONTEND_BASE_URL or SITE_URL}/api/payments/verify?{urlencode({'doc': doc_num, 't': date_str})}"
        primary = _hex_to_rgb(primary_hex)
        slate_900, slate_700, slate_500, slate_300, white = (15, 23, 42), (51, 65, 85), (100, 116, 139), (203, 213, 225), (255, 255, 255)
        status_color = (16, 185, 129) if is_paid else ((245, 158, 11) if status_display.lower() in {"pending", "initiated"} else (220, 38, 38))

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=14)
        pdf.add_page()
        page_w = 210
        body_w = page_w - 24

        def _draw_box(x: float, y: float, w: float, h: float, radius: float = 0, style: str = ""):
            rounded = getattr(pdf, "rounded_rect", None)
            if callable(rounded):
                try:
                    rounded(x, y, w, h, radius, style=style)
                    return
                except Exception:
                    pass
            pdf.rect(x, y, w, h, style)

        pdf.set_font("Helvetica", "B", 46)
        pdf.set_text_color(235, 240, 248)
        pdf.set_xy(20, 115)
        pdf.cell(170, 14, f"{BRAND}", align="C")
        header_bands = [_hex_to_rgb("#2563EB"), _hex_to_rgb("#1D4ED8"), _hex_to_rgb("#3B82F6")]
        band_w = page_w / 3
        for i, band in enumerate(header_bands):
            pdf.set_fill_color(*band)
            pdf.rect(band_w * i, 0, band_w + 1, 42, "F")
        seg_w = page_w / 4
        for i, band in enumerate(_V7_STRIPE_COLORS):
            pdf.set_fill_color(*band)
            pdf.rect(seg_w * i, 42, seg_w + 1, 4, "F")
        logo_path = _get_document_logo_temp_path()
        if logo_path:
            try:
                pdf.image(logo_path, x=12, y=9, w=16, h=16)
            except Exception:
                pass
        pdf.set_text_color(*white)
        pdf.set_xy(31, 10)
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(90, 8, brand_display)
        pdf.set_xy(31, 19)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(90, 5, f"{title} - Secure Digital Payment Document")
        pdf.set_xy(120, 10)
        pdf.set_font("Helvetica", "B", 24)
        pdf.cell(78, 10, title, align="R")
        pdf.set_xy(120, 21)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(78, 5, date_str, align="R")
        pdf.set_fill_color(*status_color)
        _draw_box(160, 50, 36, 10, radius=2, style="F")
        pdf.set_xy(160, 52)
        pdf.set_text_color(*white)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(36, 5, status_display.upper(), align="C")
        pdf.set_fill_color(245, 247, 255)
        _draw_box(12, 62, body_w, 150, radius=2, style="F")
        pdf.set_draw_color(*slate_300)
        _draw_box(12, 62, body_w, 150, radius=2, style="D")
        card_w = (body_w - 16) / 2
        left_x, right_x, card_y, pad = 16, 16 + ((body_w - 16) / 2) + 8, 70, 4
        for x in [left_x, right_x]:
            pdf.set_fill_color(*white)
            _draw_box(x, card_y, card_w, 30, radius=1.8, style="F")
            pdf.set_draw_color(*slate_300)
            _draw_box(x, card_y, card_w, 30, radius=1.8, style="D")
        pdf.set_text_color(*slate_500)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_xy(left_x + pad, card_y + 3)
        pdf.cell(40, 4, "BILL TO")
        pdf.set_xy(left_x + pad, card_y + 10)
        pdf.set_text_color(*slate_900)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(card_w - pad * 2, 5, user_name or "Customer")
        pdf.set_xy(left_x + pad, card_y + 17)
        pdf.set_text_color(*slate_700)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(card_w - pad * 2, 5, user_email)
        rx = right_x + pad
        pdf.set_text_color(*slate_500)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_xy(rx, card_y + 3)
        pdf.cell(card_w - pad * 2, 4, "DOCUMENT INFO")

        def _compact(value: str, max_len: int = 28) -> str:
            return value if len(value) <= max_len else f"{value[:12]}...{value[-8:]}"

        for i, (lbl, val) in enumerate([
            ("ID Facture" if is_fr else "Invoice ID", _compact(doc_num, 26)),
            ("ID Transaction" if is_fr else "Transaction ID", _compact(transaction_id, 30)),
            ("Méthode" if is_fr else "Method", _compact(method_display, 24)),
            ("Horodatage" if is_fr else "Timestamp", _compact(date_str, 26)),
        ]):
            y = card_y + 9 + (i * 5.3)
            pdf.set_xy(rx, y)
            pdf.set_text_color(*slate_500)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(23, 4, f"{lbl}:")
            pdf.set_xy(rx + 23, y)
            pdf.set_text_color(*slate_700)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(card_w - (pad * 2) - 23, 4, val)

        table_y = 108
        pdf.set_fill_color(*primary)
        pdf.rect(16, table_y, body_w - 8, 8, "F")
        pdf.set_text_color(*white)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(20, table_y + 2)
        pdf.cell(80, 4, "DESCRIPTION")
        pdf.set_xy(120, table_y + 2)
        pdf.cell(30, 4, "STATUT" if is_fr else "STATUS", align="C")
        pdf.set_xy(155, table_y + 2)
        pdf.cell(35, 4, "MONTANT" if is_fr else "AMOUNT", align="R")
        pdf.set_text_color(*slate_900)
        pdf.set_font("Helvetica", "", 9)
        row_y = table_y + 8
        rows = [
            (f"{_L('base_subscription_price', lang)} - {plan_name} Plan ({billing.title()})", status_display, subtotal),
            (f"{_L('applicable_tax', lang)} ({tax_jurisdiction} @ {tax_rate * 100:.2f}%)", "-", tax_amount),
            (_L("payment_processing_fee", lang), "-", fee_amount),
        ]
        for idx, (desc, st, amt) in enumerate(rows):
            fill = (255, 255, 255) if idx % 2 == 0 else (248, 250, 252)
            pdf.set_fill_color(*fill)
            pdf.rect(16, row_y, body_w - 8, 9, "F")
            pdf.set_draw_color(*slate_300)
            pdf.rect(16, row_y, body_w - 8, 9, "D")
            pdf.set_xy(20, row_y + 2.5)
            pdf.cell(95, 4, desc[:56])
            pdf.set_xy(120, row_y + 2.5)
            pdf.set_text_color(*(status_color if st not in {"-", ""} else slate_700))
            pdf.cell(30, 4, st, align="C")
            pdf.set_text_color(*slate_900)
            pdf.set_xy(155, row_y + 2.5)
            pdf.cell(35, 4, f"{currency} {amt:,.2f}", align="R")
            row_y += 9
        pdf.set_fill_color(*slate_900)
        pdf.rect(16, row_y + 1, body_w - 8, 11, "F")
        pdf.set_text_color(*white)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_xy(20, row_y + 4)
        pdf.cell(70, 4, _L("total_you_pay", lang).upper())
        pdf.set_xy(120, row_y + 4)
        pdf.cell(70, 4, f"{currency} {total_amount:,.2f}", align="R")
        wm_y = row_y + 22
        pdf.set_text_color(224, 231, 240)
        pdf.set_font("Helvetica", "B", 26)
        pdf.set_xy(16, wm_y)
        pdf.cell(body_w - 8, 9, "VERIFIED COPY", align="C")
        pdf.set_text_color(210, 218, 230)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_xy(16, wm_y + 9)
        pdf.cell(body_w - 8, 6, brand_display.upper(), align="C")
        pdf.set_text_color(206, 214, 226)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_xy(16, wm_y + 16)
        pdf.cell(body_w - 8, 4, f"{title} - {doc_num}", align="C")
        pdf.set_text_color(196, 204, 216)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_xy(16, wm_y + 21)
        pdf.cell(body_w - 8, 4, RECEIPT_VERSION, align="C")

        qr_path = None
        if show_qr:
            try:
                import qrcode
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=1)
                qr.add_data(verify_api_url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff").convert("RGB")
                fd, qr_path = tempfile.mkstemp(prefix="qr-v2-", suffix=".png")
                qr_img.save(os.fdopen(fd, "wb"), format="PNG")
            except Exception:
                qr_path = None
        footer_y = 232
        if qr_path:
            try:
                pdf.image(qr_path, x=16, y=footer_y, w=24, h=24)
            except Exception:
                pass
        pdf.set_text_color(*slate_500)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_xy(44, footer_y)
        pdf.multi_cell(145, 4.2, f"Scan to verify this {title.lower()}\nReport Hash: {verify_hash}\nSignature: {verify_signature or 'DISABLED'}\n{company_info} - {footer_text}")
        if qr_path:
            try:
                os.remove(qr_path)
            except Exception:
                pass
        return enforce_pdf_v15_enterprise(bytes(pdf.output()), f"receipt_renderer_{doc_type}_{payment_id}")
    except Exception as exc:
        _logger.warning(f"Enterprise PDF renderer v2 fallback: {exc}")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_fill_color(*_hex_to_rgb(primary_hex))
    pdf.rect(0, 0, 210, 50, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_xy(16, 12)
    pdf.cell(0, 10, title)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(16, 24)
    pdf.cell(0, 6, f"{brand_display} • {date_str}")
    pdf.set_y(68)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, user_name or "Customer", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, user_email, ln=True)
    pdf.ln(8)
    pdf.cell(0, 8, f"Plan: {plan_name} ({billing.title()})", ln=True)
    pdf.cell(0, 8, f"Method: {method_display}", ln=True)
    pdf.cell(0, 8, f"Status: {status_display}", ln=True)
    pdf.cell(0, 8, f"Amount: ${amount:,.2f}", ln=True)
    pdf.cell(0, 8, f"Product Type: {_display_product_type(payment.get('product_type'))}", ln=True)
    return enforce_pdf_v15_enterprise(bytes(pdf.output()), f"receipt_renderer_fallback_{doc_type}_{payment_id}")
