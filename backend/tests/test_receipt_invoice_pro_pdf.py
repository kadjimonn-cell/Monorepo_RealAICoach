"""Permanent test suite: enterprise pro Payment Receipt/Invoice PDF (PDF v15)."""

import sys

sys.path.insert(0, "/app/backend")

import pytest

from services.receipt_pdf_pro import generate_receipt_pdf_pro, _fmt_money
from utils.receipt_pdf_renderer import generate_pdf_from_payment

BRANDING = {
    "brand_name": "RealAICoach",
    "primary_color": "#2563EB",
    "footer_text": "Thank you for your business!",
    "company_info": "support@realaicoach.app",
    "show_qr_code": True,
}


def _payment(**overrides):
    # Canonical platform subscription prices: Free $0.00 / Basic $5.99 / Premium $15.99
    base = {
        "payment_id": "pay_abc12345",
        "id": "pay_abc12345",
        "transaction_id": "txn_9f8e7d6c5b4a",
        "plan_id": "basic",
        "amount": 5.99,
        "subtotal": 5.99,
        "tax_amount": 0.49,
        "processing_fee": 0.70,
        "amount_gross": 6.48,
        "total_amount": 7.18,
        "tax_rate": 0.0825,
        "jurisdiction": {"country": "US", "state": "TX"},
        "status": "completed",
        "created_at": "2026-06-15T14:30:00Z",
        "billing_period": "monthly",
        "currency": "USD",
        "payment_method": "stripe",
        "transparency_mode": True,
    }
    base.update(overrides)
    return base


def _text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_receipt_pdf_generates_valid_pdf():
    data = generate_receipt_pdf_pro("receipt", _payment(), "Jane Doe", "jane@example.com", BRANDING)
    assert data.startswith(b"%PDF")
    text = _text(data)
    assert "RECEIPT" in text
    assert "RCT-20260615-PAY_ABC1" in text
    assert "Jane Doe" in text
    assert "jane@example.com" in text
    assert "PAID" in text


def test_invoice_pdf_generates_valid_pdf():
    data = generate_receipt_pdf_pro("invoice", _payment(), "Jane Doe", "jane@example.com", BRANDING)
    text = _text(data)
    assert "INVOICE" in text
    assert "INV-20260615-PAY_ABC1" in text


def test_totals_and_line_items_present():
    text = _text(generate_receipt_pdf_pro("receipt", _payment(), "Jane Doe", "jane@example.com", BRANDING))
    assert "USD 5.99" in text
    assert "USD 0.49" in text
    assert "USD 0.70" in text
    assert "USD 7.18" in text
    assert "US-TX @ 8.25%" in text
    assert "TOTAL YOU PAY" in text


def test_canonical_premium_plan_price():
    p = _payment(plan_id="premium", amount=15.99, subtotal=15.99, tax_amount=0.0, processing_fee=0.0, amount_gross=15.99, total_amount=15.99)
    text = _text(generate_receipt_pdf_pro("receipt", p, "Jane Doe", "jane@example.com", BRANDING))
    assert "Premium" in text
    assert "USD 15.99" in text


def test_no_global_v15_policy_chrome_on_output():
    data = generate_pdf_from_payment("receipt", _payment(), "Jane Doe", "jane@example.com", branding_override=BRANDING)
    text = _text(data)
    assert "GLOBAL PDF V15 POLICY ACTIVE" not in text
    assert "RealAICoach PDF v15" not in text
    assert "PDF v15" not in text


def test_timeline_present():
    text = _text(generate_receipt_pdf_pro("receipt", _payment(), "Jane Doe", "jane@example.com", BRANDING))
    assert "PAYMENT TIMELINE" in text
    for step in ("Initiated", "Processed", "Confirmed"):
        assert step in text


def test_explainability_panel_transparency_on_off():
    on = _text(generate_receipt_pdf_pro("receipt", _payment(), "J", "j@x.com", BRANDING))
    off = _text(generate_receipt_pdf_pro("receipt", _payment(transparency_mode=False), "J", "j@x.com", BRANDING))
    assert "RECEIPT EXPLAINABILITY" in on.upper()
    assert "RECEIPT EXPLAINABILITY" not in off.upper()


def test_hash_and_signature_present():
    text = _text(generate_receipt_pdf_pro("receipt", _payment(), "J", "j@x.com", BRANDING))
    assert "HASH" in text
    assert "SIGN" in text


@pytest.mark.parametrize("lang,expected_title,expected_status", [
    ("fr", "FACTURE", "PAY"),
    ("es", "FACTURA", "PAGADO"),
    ("pt", "FATURA", "PAGO"),
])
def test_i18n_localized_invoice(lang, expected_title, expected_status):
    p = _payment(locale=lang, language=lang)
    text = _text(generate_receipt_pdf_pro("invoice", p, "J", "j@x.com", BRANDING))
    assert expected_title in text
    assert expected_status in text


def test_arabic_locale_falls_back_to_english():
    p = _payment(locale="ar", language="ar")
    text = _text(generate_receipt_pdf_pro("receipt", p, "J", "j@x.com", BRANDING))
    assert "RECEIPT" in text


@pytest.mark.parametrize("status,label", [
    ("initiated", "PENDING"),
    ("failed", "FAILED"),
])
def test_status_variants(status, label):
    text = _text(generate_receipt_pdf_pro("receipt", _payment(status=status), "J", "j@x.com", BRANDING))
    assert label in text


def test_no_decimal_currency_formatting():
    assert _fmt_money("XOF", 18000.0) == "XOF 18,000"
    assert _fmt_money("JPY", 4400.4) == "JPY 4,400"
    assert _fmt_money("USD", 29.99) == "USD 29.99"
    p = _payment(currency="XOF", subtotal=18000, tax_amount=0, processing_fee=540, amount_gross=18000, total_amount=18540)
    text = _text(generate_receipt_pdf_pro("receipt", p, "J", "j@x.com", BRANDING))
    assert "XOF 18,540" in text


def test_wrapper_delegates_to_pro_and_enforces_v15():
    data = generate_pdf_from_payment("receipt", _payment(), "Jane Doe", "jane@example.com", branding_override=BRANDING)
    assert data.startswith(b"%PDF")
    text = _text(data)
    assert "PAYMENT TIMELINE" in text


def test_wrapper_falls_back_on_pro_failure(monkeypatch):
    import utils.receipt_pdf_renderer as renderer_mod
    import services.receipt_pdf_pro as pro_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(pro_mod, "generate_receipt_pdf_pro", _boom)
    data = renderer_mod.generate_pdf_from_payment("receipt", _payment(), "Jane Doe", "jane@example.com", branding_override=BRANDING)
    assert data.startswith(b"%PDF")


def test_qr_toggle_respected():
    no_qr_branding = dict(BRANDING, show_qr_code=False)
    data = generate_receipt_pdf_pro("receipt", _payment(), "J", "j@x.com", no_qr_branding)
    assert data.startswith(b"%PDF")


def test_brand_watermark_fills_blank_space():
    text = _text(generate_receipt_pdf_pro("receipt", _payment(), "Jane Doe", "jane@example.com", BRANDING))
    assert text.count("RealAICoach") >= 3, f"expected watermark brand lockup, got {text.count('RealAICoach')} occurrences"
    assert text.count("RCT-20260615-PAY_ABC1") >= 4, "expected watermark doc-number line"


def test_brand_watermark_present_when_transparency_off():
    text = _text(generate_receipt_pdf_pro("receipt", _payment(transparency_mode=False), "Jane Doe", "jane@example.com", BRANDING))
    assert text.count("RealAICoach") >= 3


def test_brand_watermark_on_invoice():
    text = _text(generate_receipt_pdf_pro("invoice", _payment(), "Jane Doe", "jane@example.com", BRANDING))
    assert text.count("RealAICoach") >= 3
    assert text.count("INV-20260615-PAY_ABC1") >= 4
