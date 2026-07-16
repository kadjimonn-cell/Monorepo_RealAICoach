"""Enterprise pro-grade Payment Receipt / Invoice PDF renderer (PDF v15).

Single source of visual truth for customer payment documents. Mirrors the
enterprise chrome used by the GTEC C5 and Job Offer Letter generators:
dual-tone accent strips, v7 quad stripe, branded header, status seal,
payment timeline, explainability panel and QR trust footer.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

INK = HexColor("#0F172A")
SLATE = HexColor("#475569")
GREY = HexColor("#64748B")
SLATE_SOFT = HexColor("#F1F5F9")
BORDER_SOFT = HexColor("#E2E8F0")
TEAL = HexColor("#14B8A6")
TEAL_DEEP = HexColor("#0F766E")
INDIGO = HexColor("#4F46E5")
AMBER = HexColor("#F59E0B")
SUCCESS = HexColor("#047857")
DANGER = HexColor("#B91C1C")
EMERALD_50 = HexColor("#ECFDF5")
AMBER_50 = HexColor("#FFF7ED")
RED_50 = HexColor("#FEF2F2")
V7_STRIPES = [HexColor("#3B82F6"), HexColor("#8B5CF6"), HexColor("#EC4899"), HexColor("#06D6A0")]

_NO_DECIMAL = {"JPY", "KRW", "XOF", "XAF"}

_STATUS_I18N = {
    "paid": {"en": "PAID", "fr": "PAYÉ", "es": "PAGADO", "pt": "PAGO"},
    "pending": {"en": "PENDING", "fr": "EN ATTENTE", "es": "PENDIENTE", "pt": "PENDENTE"},
    "failed": {"en": "FAILED", "fr": "ÉCHOUÉ", "es": "FALLIDO", "pt": "FALHOU"},
}

_TITLES = {
    "receipt": {"en": "RECEIPT", "fr": "REÇU", "es": "RECIBO", "pt": "RECIBO"},
    "invoice": {"en": "INVOICE", "fr": "FACTURE", "es": "FACTURA", "pt": "FATURA"},
}


def _fmt_money(currency: str, value: float) -> str:
    if currency in _NO_DECIMAL:
        return f"{currency} {int(round(value)):,}"
    return f"{currency} {value:,.2f}"


def _fit(pdf: Canvas, text: str, font: str, size: float, max_w: float) -> str:
    text = str(text or "").strip()
    if pdf.stringWidth(text, font, size) <= max_w:
        return text
    while text and pdf.stringWidth(text + "...", font, size) > max_w:
        text = text[:-1]
    return text + "..." if text else ""


def generate_receipt_pdf_pro(doc_type: str, payment: dict, user_name: str, user_email: str, branding: dict) -> bytes:
    from utils.receipt_generator import (
        BRAND,
        SITE_URL,
        FRONTEND_BASE_URL,
        RECEIPT_VERSION,
        SUPPORT_EMAIL,
        _L,
        _detect_locale,
        _display_product_type,
        format_payment_method_label,
        format_payment_status_label,
    )
    from services.pdf_v15_theme import get_canonical_logo_tile_path

    brand_display = branding.get("brand_name", BRAND)
    primary_hex = branding.get("primary_color", "#2563EB")
    footer_text = branding.get("footer_text", "Thank you for your business!")
    company_info = branding.get("company_info", SUPPORT_EMAIL)
    show_qr = branding.get("show_qr_code", True)
    PRIMARY = HexColor(primary_hex if len(str(primary_hex).lstrip("#")) == 6 else "#2563EB")

    lang_raw = _detect_locale(payment)
    lang = lang_raw if lang_raw in {"en", "fr", "es", "pt"} else "en"

    plan_names = {"basic": "Basic", "premium": "Premium", "free": "Free"}
    plan_name = plan_names.get(payment.get("plan_id", ""), payment.get("plan_id", "Unknown"))
    status = str(payment.get("status", "completed"))
    created = payment.get("created_at", "")
    payment_id = payment.get("payment_id", payment.get("id", "N/A"))
    billing = str(payment.get("billing_period", "monthly") or "monthly")
    amount = float(payment.get("amount", 0) or 0)

    try:
        d = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
        date_str = d.strftime("%B %d, %Y")
        time_str = d.strftime("%H:%M UTC")
        date_short = d.strftime("%Y-%m-%d")
    except Exception:
        date_str = str(created)[:10]
        time_str = ""
        date_short = str(created)[:10]

    doc_prefix = "INV" if doc_type == "invoice" else "RCT"
    doc_num = f"{doc_prefix}-{date_short.replace('-', '')}-{str(payment_id)[:8].upper()}" if payment_id != "N/A" else f"{doc_prefix}-{date_short.replace('-', '')}"
    title = _TITLES[doc_type][lang]

    method_display = format_payment_method_label(payment.get("payment_method", "card"))
    status_display = format_payment_status_label(status)
    status_key = "paid" if status_display.lower() in {"paid", "completed", "success"} else (
        "pending" if status_display.lower() in {"pending", "initiated"} else "failed")
    status_label = _STATUS_I18N[status_key][lang] if status_key != "failed" or status_display.lower() in {"failed", "error"} else (
        _STATUS_I18N["failed"][lang] if status_display.lower() in {"failed", "error"} else status_display.upper())
    STATUS_COLOR = SUCCESS if status_key == "paid" else (AMBER if status_key == "pending" else DANGER)
    STATUS_BG = EMERALD_50 if status_key == "paid" else (AMBER_50 if status_key == "pending" else RED_50)

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
    transparency_mode = bool(payment.get("transparency_mode", True))

    secret = os.environ.get("PAYMENT_EXPORT_SIGNATURE_SECRET") or os.environ.get("JWT_SECRET") or ""
    sig_payload = f"{doc_num}|{transaction_id}|{user_email}|{total_amount:.2f}|{currency}|{date_short}|{status_display}"
    verify_hash = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()
    verify_signature = hmac.new(secret.encode("utf-8"), sig_payload.encode("utf-8"), hashlib.sha256).hexdigest() if secret else ""
    verify_api_url = f"{FRONTEND_BASE_URL or SITE_URL}/api/payments/verify?{urlencode({'doc': doc_num, 't': date_str})}"

    buf = BytesIO()
    W, H = letter
    pdf = Canvas(buf, pagesize=letter)
    pdf.setTitle(f"{title} {doc_num} - {brand_display}")
    pdf.setAuthor(brand_display)
    MX = 40
    CW = W - (2 * MX)

    # ── Watermark ────────────────────────────────────────────────────────
    pdf.saveState()
    pdf.setFillColor(STATUS_COLOR if status_key != "paid" else SLATE)
    pdf.setFillAlpha(0.045)
    pdf.setFont("Helvetica-Bold", 92)
    pdf.translate(W / 2, H / 2)
    pdf.rotate(30)
    pdf.drawCentredString(0, 0, _L("verified_copy", lang) if status_key == "paid" else status_label)
    pdf.restoreState()

    # ── Top accent strips ────────────────────────────────────────────────
    pdf.setFillColor(TEAL)
    pdf.rect(0, H - 4, W * 0.55, 4, stroke=0, fill=1)
    pdf.setFillColor(PRIMARY)
    pdf.rect(W * 0.55, H - 4, W * 0.45, 4, stroke=0, fill=1)

    # ── Header bar ───────────────────────────────────────────────────────
    header_h = 76
    header_y = H - 4 - header_h
    pdf.setFillColor(PRIMARY)
    pdf.rect(0, header_y, W, header_h, stroke=0, fill=1)
    pdf.setFillColor(INDIGO)
    pdf.rect(W * 0.72, header_y, W * 0.28, header_h, stroke=0, fill=1)
    pdf.setFillAlpha(0.35)
    pdf.setFillColor(PRIMARY)
    pdf.rect(W * 0.72, header_y, W * 0.28, header_h, stroke=0, fill=1)
    pdf.setFillAlpha(1.0)

    # v7 quad stripe under header
    seg = W / 4
    for i, c in enumerate(V7_STRIPES):
        pdf.setFillColor(c)
        pdf.rect(seg * i, header_y - 3, seg + 1, 3, stroke=0, fill=1)

    # Logo tile
    tile = 52
    tile_x, tile_y = MX, header_y + (header_h - tile) / 2
    pdf.setFillColor(white)
    pdf.roundRect(tile_x, tile_y, tile, tile, 6, stroke=0, fill=1)
    logo_path = get_canonical_logo_tile_path()
    try:
        if logo_path and os.path.exists(logo_path):
            pdf.drawImage(logo_path, tile_x + 6, tile_y + 6, width=tile - 12, height=tile - 12, mask="auto", preserveAspectRatio=True)
    except Exception:
        pass

    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(tile_x + tile + 12, header_y + header_h - 28, brand_display)
    pdf.setFillColor(HexColor("#CCFBF1"))
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(tile_x + tile + 12, header_y + header_h - 43, f"{_L('receipt_title', lang)}  •  {RECEIPT_VERSION}")
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawRightString(W - MX, header_y + header_h - 24, company_info)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(W - MX, header_y + header_h - 37, SITE_URL.replace("https://", ""))
    pdf.setFont("Helvetica", 7.5)
    pdf.drawRightString(W - MX, header_y + header_h - 50, f"{date_str}{('  •  ' + time_str) if time_str else ''}")

    # ── Masthead: giant title + doc number + status seal ─────────────────
    mast_y = header_y - 3 - 58
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 32)
    pdf.drawString(MX, mast_y + 16, title)
    pdf.setFillColor(GREY)
    pdf.setFont("Courier-Bold", 10.5)
    pdf.drawString(MX, mast_y + 2, doc_num)

    seal_w, seal_h = 132, 30
    seal_x, seal_y = W - MX - seal_w, mast_y + 2
    pdf.setFillColor(STATUS_BG)
    pdf.setStrokeColor(STATUS_COLOR)
    pdf.setLineWidth(1.1)
    pdf.roundRect(seal_x, seal_y, seal_w, seal_h, 15, stroke=1, fill=1)
    pdf.setFillColor(STATUS_COLOR)
    pdf.circle(seal_x + 16, seal_y + seal_h / 2, 4, stroke=0, fill=1)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(seal_x + 27, seal_y + seal_h / 2 - 4, _fit(pdf, status_label, "Helvetica-Bold", 11, seal_w - 34))

    # ── Bill To / Document Info cards ────────────────────────────────────
    card_h = 86
    card_y = mast_y - 14 - card_h
    card_w = (CW - 12) / 2

    for cx, heading in ((MX, _L("billed_to", lang).upper()), (MX + card_w + 12, ("INFOS DOCUMENT" if lang == "fr" else "INFO DEL DOCUMENTO" if lang == "es" else "INFO DO DOCUMENTO" if lang == "pt" else "DOCUMENT INFO"))):
        pdf.setFillColor(white)
        pdf.setStrokeColor(BORDER_SOFT)
        pdf.setLineWidth(1)
        pdf.roundRect(cx, card_y, card_w, card_h, 8, stroke=1, fill=1)
        pdf.setFillColor(TEAL)
        pdf.rect(cx, card_y, 3.5, card_h, stroke=0, fill=1)
        pdf.setFillColor(GREY)
        pdf.setFont("Helvetica-Bold", 7.4)
        pdf.drawString(cx + 12, card_y + card_h - 15, heading)

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 12.5)
    pdf.drawString(MX + 12, card_y + card_h - 34, _fit(pdf, user_name or "Customer", "Helvetica-Bold", 12.5, card_w - 24))
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(MX + 12, card_y + card_h - 49, _fit(pdf, user_email, "Helvetica", 9, card_w - 24))
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(MX + 12, card_y + card_h - 64, f"{plan_name} Plan  •  {billing.title()}")
    pdf.drawString(MX + 12, card_y + card_h - 77, _display_product_type(payment.get("product_type")))

    rx = MX + card_w + 12 + 12
    info_rows = [
        (("ID Facture" if lang == "fr" else "Invoice ID") if doc_type == "invoice" else ("ID Reçu" if lang == "fr" else "Receipt ID"), doc_num),
        (_L("transaction_id", lang), transaction_id if len(transaction_id) <= 30 else f"{transaction_id[:14]}...{transaction_id[-8:]}"),
        (_L("method", lang), method_display),
        ("Horodatage" if lang == "fr" else "Timestamp", f"{date_str} {time_str}".strip()),
    ]
    for i, (lbl, val) in enumerate(info_rows):
        yy = card_y + card_h - 30 - (i * 14.5)
        pdf.setFillColor(GREY)
        pdf.setFont("Helvetica", 7.8)
        pdf.drawString(rx, yy, f"{lbl}:")
        pdf.setFillColor(INK)
        pdf.setFont("Courier-Bold", 8)
        pdf.drawRightString(MX + CW - 12, yy, _fit(pdf, val, "Courier-Bold", 8, card_w - 100))

    # ── Payment timeline strip ───────────────────────────────────────────
    tl_h = 52
    tl_y = card_y - 12 - tl_h
    pdf.setFillColor(SLATE_SOFT)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(MX, tl_y, CW, tl_h, 8, stroke=1, fill=1)
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica-Bold", 7.4)
    tl_title = {"en": "PAYMENT TIMELINE", "fr": "CHRONOLOGIE DU PAIEMENT", "es": "CRONOLOGÍA DEL PAGO", "pt": "LINHA DO TEMPO DO PAGAMENTO"}[lang]
    pdf.drawString(MX + 12, tl_y + tl_h - 14, tl_title)

    steps = [
        {"en": "Initiated", "fr": "Initié", "es": "Iniciado", "pt": "Iniciado"}[lang],
        {"en": "Processed", "fr": "Traité", "es": "Procesado", "pt": "Processado"}[lang],
        {"en": "Confirmed", "fr": "Confirmé", "es": "Confirmado", "pt": "Confirmado"}[lang],
    ]
    done_steps = 3 if status_key == "paid" else (1 if status_key == "pending" else 2)
    step_span = (CW - 80) / 2
    line_y = tl_y + 20
    for i in range(3):
        sx = MX + 40 + (i * step_span)
        if i < 2:
            pdf.setStrokeColor(STATUS_COLOR if (i + 1) < done_steps else BORDER_SOFT)
            pdf.setLineWidth(2)
            pdf.line(sx + 7, line_y, sx + step_span - 7, line_y)
        filled = i < done_steps
        node_color = STATUS_COLOR if filled else BORDER_SOFT
        pdf.setFillColor(node_color)
        pdf.circle(sx, line_y, 5.5, stroke=0, fill=1)
        if filled:
            pdf.setFillColor(white)
            pdf.circle(sx, line_y, 2, stroke=0, fill=1)
        pdf.setFillColor(INK if filled else GREY)
        pdf.setFont("Helvetica-Bold" if filled else "Helvetica", 7.6)
        pdf.drawCentredString(sx, tl_y + 6, steps[i])

    # ── Line items ledger ────────────────────────────────────────────────
    tbl_y_top = tl_y - 14
    row_h = 21
    hdr_h = 20
    pdf.setFillColor(PRIMARY)
    pdf.roundRect(MX, tbl_y_top - hdr_h, CW, hdr_h, 4, stroke=0, fill=1)
    pdf.rect(MX, tbl_y_top - hdr_h, CW, 6, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(MX + 12, tbl_y_top - 13.5, _L("description", lang).upper())
    pdf.drawCentredString(MX + CW - 170, tbl_y_top - 13.5, _L("status", lang))
    pdf.drawRightString(MX + CW - 12, tbl_y_top - 13.5, _L("amount", lang).upper())

    rows = [
        (f"{_L('base_subscription_price', lang)} — {plan_name} ({billing.title()})", status_label, subtotal),
        (f"{_L('applicable_tax', lang)} ({tax_jurisdiction} @ {tax_rate * 100:.2f}%)", "—", tax_amount),
        (_L("payment_processing_fee", lang), "—", fee_amount),
    ]
    ry = tbl_y_top - hdr_h
    for idx, (desc, st, amt) in enumerate(rows):
        ry -= row_h
        pdf.setFillColor(white if idx % 2 == 0 else HexColor("#F8FAFC"))
        pdf.rect(MX, ry, CW, row_h, stroke=0, fill=1)
        pdf.setStrokeColor(BORDER_SOFT)
        pdf.setLineWidth(0.5)
        pdf.line(MX, ry, MX + CW, ry)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 8.8)
        pdf.drawString(MX + 12, ry + 7.5, _fit(pdf, desc, "Helvetica", 8.8, CW - 230))
        pdf.setFillColor(STATUS_COLOR if st not in {"—", ""} else GREY)
        pdf.setFont("Helvetica-Bold" if st not in {"—", ""} else "Helvetica", 7.8)
        pdf.drawCentredString(MX + CW - 170, ry + 7.5, st)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawRightString(MX + CW - 12, ry + 7.5, _fmt_money(currency, amt))

    total_h = 30
    ry -= total_h + 2
    pdf.setFillColor(INK)
    pdf.roundRect(MX, ry, CW, total_h, 5, stroke=0, fill=1)
    pdf.setFillColor(TEAL)
    pdf.rect(MX, ry, 3.5, total_h, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 11.5)
    pdf.drawString(MX + 14, ry + 10, _L("total_you_pay", lang).upper())
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(MX + CW - 12, ry + 9, _fmt_money(currency, total_amount))

    # ── Explainability panel (transparency mode) ─────────────────────────
    if transparency_mode:
        exp_h = 74
        ry -= 12 + exp_h
        pdf.setFillColor(HexColor("#F0FDFA"))
        pdf.setStrokeColor(HexColor("#CCFBF1"))
        pdf.roundRect(MX, ry, CW, exp_h, 8, stroke=1, fill=1)
        pdf.setFillColor(TEAL_DEEP)
        pdf.setFont("Helvetica-Bold", 7.6)
        pdf.drawString(MX + 12, ry + exp_h - 14, _L("receipt_explainability", lang).upper())
        exp_rows = [
            (_L("tax_basis", lang), f"{tax_jurisdiction} @ {tax_rate * 100:.2f}%"),
            (_L("product_type", lang), _display_product_type(payment.get("product_type"))),
            (_L("fee_policy", lang), _L("fee_policy_text", lang)),
            (_L("net_payout_basis", lang), f"{_L('net_formula', lang)} = {_fmt_money(currency, total_amount - fee_amount)}"),
        ]
        for i, (lbl, val) in enumerate(exp_rows):
            yy = ry + exp_h - 28 - (i * 13)
            pdf.setFillColor(GREY)
            pdf.setFont("Helvetica", 7.6)
            pdf.drawString(MX + 12, yy, f"{lbl}:")
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 7.6)
            pdf.drawString(MX + 130, yy, _fit(pdf, val, "Helvetica-Bold", 7.6, CW - 145))
    else:
        ry -= 4

    # ── Trust / verification footer panel ────────────────────────────────
    ver_h = 84
    ry -= 12 + ver_h
    if ry < 44:
        ry = 44
    pdf.setFillColor(white)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(MX, ry, CW, ver_h, 8, stroke=1, fill=1)

    qr_drawn = False
    if show_qr:
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=1)
            qr.add_data(verify_api_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="#0f172a", back_color="#ffffff").convert("RGB")
            fd, qr_path = tempfile.mkstemp(prefix="qr-pro-", suffix=".png")
            qr_img.save(os.fdopen(fd, "wb"), format="PNG")
            pdf.drawImage(qr_path, MX + 10, ry + (ver_h - 62) / 2, width=62, height=62)
            os.remove(qr_path)
            qr_drawn = True
        except Exception:
            qr_drawn = False

    tx = MX + (84 if qr_drawn else 12)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 8.6)
    pdf.drawString(tx, ry + ver_h - 16, _L("scan_to_verify", lang))
    pdf.setFillColor(GREY)
    pdf.setFont("Courier", 6.6)
    pdf.drawString(tx, ry + ver_h - 30, f"HASH  {verify_hash}")
    pdf.drawString(tx, ry + ver_h - 41, f"SIGN  {verify_signature or 'DISABLED'}")
    pdf.setFont("Helvetica", 7.2)
    pdf.setFillColor(SLATE)
    pdf.drawString(tx, ry + ver_h - 55, _fit(pdf, verify_api_url, "Helvetica", 7.2, CW - (tx - MX) - 14))
    pdf.setFillColor(TEAL_DEEP)
    pdf.setFont("Helvetica-Bold", 7.4)
    pdf.drawString(tx, ry + 12, _fit(pdf, f"{company_info}  •  {footer_text}", "Helvetica-Bold", 7.4, CW - (tx - MX) - 14))

    # ── Brand watermark lockup (fills residual space above footer) ───────
    gap_top = ry - 10
    gap_bottom = 38
    gap_h = gap_top - gap_bottom
    if gap_h >= 48:
        cy = gap_bottom + gap_h / 2
        logo_size = max(30.0, min(60.0, gap_h * 0.58))
        wm_font = max(18.0, min(32.0, logo_size * 0.52))
        brand_w = pdf.stringWidth(brand_display, "Helvetica-Bold", wm_font)
        lockup_w = logo_size + 14 + brand_w
        lx = (W - lockup_w) / 2
        pdf.saveState()
        try:
            if logo_path and os.path.exists(logo_path):
                pdf.setFillAlpha(0.15)
                pdf.drawImage(logo_path, lx, cy - logo_size / 2 + 5, width=logo_size, height=logo_size, mask="auto", preserveAspectRatio=True)
        except Exception:
            pass
        pdf.setFillColor(INK)
        pdf.setFillAlpha(0.13)
        pdf.setFont("Helvetica-Bold", wm_font)
        pdf.drawString(lx + logo_size + 14, cy + 5 - (wm_font * 0.34), brand_display)
        pdf.setFillColor(SLATE)
        pdf.setFillAlpha(0.24)
        pdf.setFont("Helvetica-Bold", 7.6)
        pdf.drawCentredString(W / 2, cy - (logo_size / 2) - 7, f"{title}  •  {doc_num}")
        pdf.restoreState()

    # ── Bottom footer bar ────────────────────────────────────────────────
    pdf.setFillColor(TEAL)
    pdf.rect(0, 30, W, 2, stroke=0, fill=1)
    pdf.setFillColor(SLATE_SOFT)
    pdf.rect(0, 0, W, 30, stroke=0, fill=1)
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 7.2)
    pdf.drawString(MX, 12, f"{_L('auto_generated', lang)} {brand_display}  •  {doc_num}  •  {RECEIPT_VERSION}")
    pill_w, pill_h = 46, 13
    pdf.setFillColor(PRIMARY)
    pdf.roundRect(W - MX - pill_w, 9, pill_w, pill_h, 3, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(W - MX - pill_w / 2, 13, "Page 1 / 1")

    pdf.showPage()
    pdf.save()
    return buf.getvalue()
