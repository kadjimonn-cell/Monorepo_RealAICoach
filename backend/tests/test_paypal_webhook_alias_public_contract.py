import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.public_api_contract import is_public_api_path


def test_paypal_webhook_alias_is_public_api_path() -> None:
    assert is_public_api_path("/api/payments/paypal/webhook") is True


def test_paypal_webhook_alias_csrf_exempted_in_middleware_source() -> None:
    source = Path("/app/backend/middleware.py").read_text(encoding="utf-8")
    assert '"/api/payments/paypal/webhook"' in source
