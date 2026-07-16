"""Split-out HTML email builder for receipts and invoices."""

from __future__ import annotations

from datetime import datetime, timezone


def build_branded_receipt_html(
    receipt_number: str,
    user_name: str,
    user_email: str,
    plan_name: str,
    amount_usd: float,
    amount_local: float = 0,
    currency: str = "USD",
    payment_method: str = "Card",
    billing_period: str = "monthly",
    payment_date: str = "",
    renewal_date: str = "",
    gateway_fee: float = 0,
    ticket_id: str = "",
    download_url: str = "",
    payment_data: dict | None = None,
) -> str:
    from utils.receipt_generator import (
        APP_STORE_BADGE_IMAGE_URL,
        APP_STORE_URL,
        BRAND,
        GOOGLE_PLAY_BADGE_IMAGE_URL,
        GOOGLE_PLAY_URL,
        RECEIPT_VERSION,
        SUPPORT_EMAIL,
        _L,
        _detect_locale,
        _display_product_type,
        _is_french_payment,
    )

    if not payment_date:
        payment_date = datetime.now(timezone.utc).strftime("%b %d, %Y")
    currency_symbols = {"EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "CA$", "AUD": "A$", "INR": "₹", "USD": "$"}
    no_decimal = {"JPY", "KRW", "XOF", "XAF"}
    cur = currency.upper()
    sym = currency_symbols.get(cur, f"{cur} ")
    payment_data = payment_data or {}
    is_fr = _is_french_payment(payment_data)
    lang = _detect_locale(payment_data)
    transparency_mode = bool(payment_data.get("transparency_mode", True))
    subtotal_value = float(payment_data.get("subtotal", amount_local if cur != "USD" and amount_local > 0 else amount_usd) or 0)
    tax_value = float(payment_data.get("tax_amount", 0) or 0)
    fee_value = float(payment_data.get("processing_fee", gateway_fee) or 0)
    gross_value = float(payment_data.get("amount_gross", subtotal_value + tax_value) or (subtotal_value + tax_value))
    total_value = float(payment_data.get("total_amount", gross_value) or gross_value)
    tax_rate = float(payment_data.get("tax_rate", 0) or 0)
    jurisdiction = payment_data.get("jurisdiction", {}) if isinstance(payment_data.get("jurisdiction"), dict) else {}
    jurisdiction_label = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-") or "N/A"
    product_type = _display_product_type(str(payment_data.get("product_type", "education_digital_service") or "education_digital_service"))
    if cur != "USD" and amount_local > 0:
        total_display = f"{sym}{int(round(total_value)):,}" if cur in no_decimal else f"{sym}{total_value:,.2f}"
        subtotal_display = f"{sym}{int(round(subtotal_value)):,}" if cur in no_decimal else f"{sym}{subtotal_value:,.2f}"
        tax_display = f"{sym}{int(round(tax_value)):,}" if cur in no_decimal else f"{sym}{tax_value:,.2f}"
        fee_display_value = f"{sym}{int(round(fee_value)):,}" if cur in no_decimal else f"{sym}{fee_value:,.2f}"
        usd_note = f'<p style="margin:6px 0 0;font-size:11px;color:#64748B;text-align:right;">USD reference: ${amount_usd:.2f}</p>'
    else:
        subtotal_display, tax_display, fee_display_value, total_display, usd_note = f"${subtotal_value:,.2f}", f"${tax_value:,.2f}", f"${fee_value:,.2f}", f"${total_value:,.2f} USD", ""
    explainability_block = ""
    if transparency_mode:
        explainability_block = f"<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;padding:0 24px 16px;\"><tr><td class=\"em-soft\" style=\"background:#FFFFFF !important;border:1px solid #E2E8F0 !important;border-radius:12px;padding:14px;\"><p class=\"em-detail-label\" style=\"margin:0 0 10px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.8px;color:#64748B !important;\">{_L('receipt_explainability', lang)}</p><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;\"><tr><td class=\"em-detail-label\" style=\"padding:4px 0;font-size:12px;color:#64748B !important;\">{_L('tax_basis', lang)}</td><td class=\"em-detail-value\" style=\"padding:4px 0;font-size:12px;text-align:right;color:#0F172A !important;\">{jurisdiction_label} @ {tax_rate * 100:.2f}%</td></tr><tr><td class=\"em-detail-label\" style=\"padding:4px 0;font-size:12px;color:#64748B !important;\">{_L('product_type', lang)}</td><td class=\"em-detail-value\" style=\"padding:4px 0;font-size:12px;text-align:right;color:#0F172A !important;\">{product_type}</td></tr></table></td></tr></table>"
    download_btn = f"<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin:20px auto 0;\"><tr><td style=\"border-radius:10px;background:#1E40AF;\"><a href=\"{download_url}\" target=\"_blank\" style=\"display:inline-block;padding:12px 30px;color:#fff;font-size:13px;font-weight:700;text-decoration:none;\">{_L('download_pdf', lang)}</a></td></tr></table>" if download_url else ""
    renewal_row = f"<tr><td class=\"em-detail-label\" style=\"padding:4px 0;font-size:12px;color:#CBD5E1 !important;\">Next Renewal</td><td class=\"em-detail-value\" style=\"padding:4px 0;font-size:12px;text-align:right;color:#FFFFFF !important;\">{renewal_date}</td></tr>" if renewal_date else ""
    fee_row = f"<tr><td class=\"em-summary-row em-summary-label em-summary-border\" style=\"padding:10px 16px;background:#FFFFFF !important;color:#334155 !important;font-size:13px;font-weight:700;border-bottom:1px solid #E2E8F0 !important;\">{_L('payment_processing_fee', lang)}</td><td class=\"em-summary-row em-summary-value em-summary-border\" style=\"padding:10px 16px;background:#FFFFFF !important;color:#0F172A !important;font-size:13px;font-weight:800;border-bottom:1px solid #E2E8F0 !important;text-align:right;\">{fee_display_value}</td></tr>" if fee_value > 0 else ""
    return f"""<!DOCTYPE html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body style=\"margin:0;padding:0;background-color:#EEF2FF;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;\"><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;background:#EEF2FF;\"><tr><td style=\"padding:24px 16px;\"><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:620px;margin:0 auto;width:100%;\"><tr><td style=\"background:#FFFFFF;border:1px solid #DBEAFE;border-radius:20px;overflow:hidden;box-shadow:0 12px 36px rgba(37,99,235,0.12);\"><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;background:linear-gradient(135deg,#1D4ED8,#4F46E5,#0EA5E9);\"><tr><td style=\"padding:26px 24px 22px;\"><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;\"><tr><td><p style=\"margin:0;font-size:24px;font-weight:900;color:#FFFFFF;letter-spacing:-0.5px;\">{BRAND}</p><p style=\"margin:6px 0 0;font-size:12px;color:#DBEAFE;font-weight:600;\">{_L('receipt_title', lang)}</p></td><td style=\"text-align:right;\"><span style=\"display:inline-block;background:#10B981;color:#FFFFFF;padding:5px 12px;border-radius:999px;font-size:10px;font-weight:800;letter-spacing:0.8px;\">{_L('paid', lang)}</span><p style=\"margin:8px 0 0;font-size:11px;color:#E0E7FF;font-weight:600;\">{payment_date}</p></td></tr></table><p style=\"margin:14px 0 0;font-size:13px;color:#E0E7FF;\">{_L('thanks', lang)} {user_name}, {_L('payment_success_msg', lang)}</p></td></tr></table><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;padding:22px 24px 18px;\"><tr><td style=\"background:#FFFFFF !important;border:1px solid #E2E8F0 !important;border-radius:14px;padding:12px 14px;vertical-align:top;\"><p style=\"margin:0 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;font-weight:700;color:#64748B !important;\">{_L('receipt_number', lang)}</p><p style=\"margin:0;font-size:12px;font-weight:700;font-family:monospace;color:#0F172A !important;\">{receipt_number}</p></td><td style=\"width:10px;\">&nbsp;</td><td style=\"background:#FFFFFF !important;border:1px solid #E2E8F0 !important;border-radius:14px;padding:12px 14px;vertical-align:top;\"><p style=\"margin:0 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;font-weight:700;color:#64748B !important;\">{_L('billed_to', lang)}</p><p style=\"margin:0;font-size:12px;font-weight:700;color:#0F172A !important;\">{user_name}</p><p style=\"margin:4px 0 0;font-size:11px;color:#64748B !important;\">{user_email}</p></td></tr></table><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;padding:0 24px 10px;border-collapse:collapse;\"><tr style=\"background:#F8FAFC;\"><td style=\"padding:11px 14px;color:#334155;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.8px;border:1px solid #E2E8F0;border-radius:10px 0 0 0;\">Description</td><td style=\"padding:11px 14px;color:#334155;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.8px;border:1px solid #E2E8F0;border-left:none;border-radius:0 10px 0 0;text-align:right;\">Amount</td></tr><tr><td style=\"padding:14px;background:#FFFFFF !important;color:#0F172A !important;font-size:14px;font-weight:800;border:1px solid #E2E8F0;border-top:none;\">{_L('base_subscription_price', lang)} — {plan_name} Plan ({billing_period.title()})</td><td style=\"padding:14px;background:#FFFFFF !important;color:#0F172A !important;font-size:14px;font-weight:800;border:1px solid #E2E8F0;border-left:none;border-top:none;text-align:right;\">{subtotal_display}</td></tr><tr><td style=\"padding:10px 16px;background:#FFFFFF !important;color:#334155 !important;font-size:13px;font-weight:700;border:1px solid #E2E8F0;border-top:none;\">{_L('applicable_tax', lang)} ({jurisdiction_label} @ {tax_rate * 100:.2f}%)</td><td style=\"padding:10px 16px;background:#FFFFFF !important;color:#0F172A !important;font-size:13px;font-weight:800;border:1px solid #E2E8F0;border-left:none;border-top:none;text-align:right;\">{tax_display}</td></tr>{fee_row}<tr style=\"background:#EEF4FF;\"><td style=\"padding:14px;color:#0F172A;font-size:16px;font-weight:900;border:1px solid #BFDBFE;border-top:none;\">{_L('total_you_pay', lang)}</td><td style=\"padding:14px;font-size:18px;font-weight:900;border:1px solid #BFDBFE;border-left:none;border-top:none;text-align:right;color:#1D4ED8;\">{total_display}</td></tr></table>{usd_note}<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;padding:0 24px 18px;\"><tr><td style=\"background:#FFFFFF !important;border:1px solid #E2E8F0 !important;border-radius:12px;padding:14px;\"><p style=\"margin:0 0 10px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.8px;color:#64748B !important;\">{'Détails du paiement' if is_fr else 'Payment Details'}</p><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;\"><tr><td style=\"padding:4px 0;font-size:12px;color:#64748B !important;\">{'Méthode' if is_fr else 'Method'}</td><td style=\"padding:4px 0;font-size:12px;text-align:right;color:#0F172A !important;\">{payment_method}</td></tr><tr><td style=\"padding:4px 0;font-size:12px;color:#64748B !important;\">{'ID Transaction' if is_fr else 'Transaction ID'}</td><td style=\"padding:4px 0;font-size:12px;text-align:right;font-family:monospace;color:#0F172A !important;\">{ticket_id or receipt_number}</td></tr>{renewal_row}</table></td></tr></table>{explainability_block}{download_btn}<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 auto 16px;\"><tr><td style=\"padding-right:6px;\"><a href=\"{GOOGLE_PLAY_URL}\" target=\"_blank\" style=\"text-decoration:none;display:inline-block;\"><img src=\"{GOOGLE_PLAY_BADGE_IMAGE_URL}\" alt=\"Get it on Google Play\" width=\"132\" style=\"display:block;width:132px;max-width:100%;height:auto;border:0;\" /></a></td><td style=\"padding-left:6px;\"><a href=\"{APP_STORE_URL}\" target=\"_blank\" style=\"text-decoration:none;display:inline-block;\"><img src=\"{APP_STORE_BADGE_IMAGE_URL}\" alt=\"Download on the App Store\" width=\"132\" style=\"display:block;width:132px;max-width:100%;height:auto;border:0;\" /></a></td></tr></table><table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;background:#F8FAFC !important;border-top:1px solid #E2E8F0 !important;\"><tr><td style=\"padding:14px 24px;text-align:center;\"><p style=\"margin:0;font-size:10px;color:#CBD5E1 !important;\">{_L('auto_generated', lang)} {BRAND}. {RECEIPT_VERSION}</p><p style=\"margin:4px 0 0;font-size:10px;color:#CBD5E1 !important;\">{_L('questions_contact', lang)} {SUPPORT_EMAIL}</p></td></tr></table></td></tr></table></td></tr></table></body></html>"""
