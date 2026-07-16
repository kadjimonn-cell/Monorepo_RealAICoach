import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes.payments_pricing_guard import extract_payment_amount_for_plan_validation


def test_document_context_prefers_base_amount_over_gross() -> None:
    payment = {
        "amount": 5.99,
        "amount_gross": 9.02,
        "total_amount": 9.53,
    }
    resolved = extract_payment_amount_for_plan_validation(payment, context="receipt_pdf")
    assert resolved == 5.99


def test_checkout_context_keeps_gross_priority() -> None:
    payment = {
        "amount": 5.99,
        "amount_gross": 9.02,
        "total_amount": 9.53,
    }
    resolved = extract_payment_amount_for_plan_validation(payment, context="payment_confirmation_email")
    assert resolved == 9.02


def test_iap_document_context_prefers_base_plan_price() -> None:
    payment = {
        "provider": "iap_google",
        "base_plan_price": 15.99,
        "amount": 21.72,
        "amount_gross": 21.72,
        "total_amount": 21.72,
    }
    resolved = extract_payment_amount_for_plan_validation(payment, context="receipt_pdf")
    assert resolved == 15.99
