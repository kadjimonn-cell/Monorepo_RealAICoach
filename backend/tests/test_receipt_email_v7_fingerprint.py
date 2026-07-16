import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.receipt_generator import build_branded_receipt_html


def test_branded_receipt_html_contains_v7_fingerprint() -> None:
    html = build_branded_receipt_html(
        receipt_number="RCT-TEST-123",
        user_name="Test User",
        user_email="test.user@example.com",
        plan_name="Basic",
        amount_usd=5.99,
        amount_local=4061,
        currency="XOF",
        payment_method="Mobile Money (FedaPay)",
        billing_period="monthly",
        payment_date="May 20, 2026",
        renewal_date="Jun 20, 2026",
        ticket_id="MMSUB_TEST",
    )
    assert 'class="em-outer"' in html
