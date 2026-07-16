from pathlib import Path


def test_waf_ip_rate_exemptions_include_payment_document_routes() -> None:
    source = Path("/app/backend/middleware.py").read_text(encoding="utf-8")
    assert '"/api/payments/receipt/"' in source
    assert '"/api/payments/invoice/"' in source
