import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.public_api_contract import is_public_api_path


def test_fedapay_callback_is_public_path() -> None:
    assert is_public_api_path("/api/fedapay/callback") is True


def test_fedapay_webhook_remains_public_path() -> None:
    assert is_public_api_path("/api/payments/fedapay/webhook") is True


def test_fedapay_status_endpoint_not_public() -> None:
    assert is_public_api_path("/api/fedapay/status/fedapay_123") is False
