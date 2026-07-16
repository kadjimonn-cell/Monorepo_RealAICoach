from pathlib import Path


def test_google_iap_custom_notification_message_includes_eticket() -> None:
    source = Path('/app/backend/routes/iap.py').read_text(encoding='utf-8')
    assert 'custom_notification_title' in source
    # IAP should not override the default confirmation message template,
    # so payments.py can inject canonical `eTicket: ...` text.
    assert 'custom_notification_message' not in source


def test_default_payment_notification_message_template_contains_eticket() -> None:
    source = Path('/app/backend/routes/payments.py').read_text(encoding='utf-8')
    assert 'eTicket: {ticket_id}' in source
