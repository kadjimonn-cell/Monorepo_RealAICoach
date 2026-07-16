from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_integrations_calendar_cancel_and_reschedule_use_uno_reservation() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert "dedupe_key = f\"calendar_event_cancelled:{event_id}:{recipient_norm}\"" in source
    assert "dedupe_key = f\"calendar_event_rescheduled:{event_id}:{new_date}:{recipient_norm}\"" in source
    assert "reserved = await reserve_dispatch_once(" in source
    assert "await mark_dispatch_status(" in source


def test_integrations_booking_confirmation_and_cancellation_use_uno_reservation() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert "guest_dedupe_key = f\"booking_created:{booking['booking_id']}:{guest_norm}\"" in source
    assert "host_dedupe_key = f\"booking_confirmed_host:{booking['booking_id']}:{host_norm}\"" in source
    assert "cancel_dedupe_key = f\"booking_cancelled:{booking_id}:{guest_email_norm}\"" in source
    assert "guest_reserved = await reserve_dispatch_once(" in source
    assert "host_reserved = await reserve_dispatch_once(" in source
    assert "reserved = await reserve_dispatch_once(" in source
    assert "await mark_dispatch_status(" in source
