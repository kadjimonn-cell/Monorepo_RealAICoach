from pathlib import Path


def test_payment_email_pricing_guard_uses_canonical_amount_variables() -> None:
    file_path = Path(__file__).resolve().parents[1] / "routes" / "payments.py"
    source = file_path.read_text(encoding="utf-8")

    assert "pricing_guard_amount" in source
    assert "pricing_guard_currency" in source
    assert 'if tx_currency_for_guard != "USD" and tx.get("amount_usd") is not None:' in source
    assert '"amount": pricing_guard_amount' in source
    assert '"amount_gross": pricing_guard_amount' in source
    assert '"total_amount": pricing_guard_amount' in source
    assert '"currency": pricing_guard_currency' in source
