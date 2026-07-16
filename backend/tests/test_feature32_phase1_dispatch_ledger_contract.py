from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_dispatch_service_exposes_reserve_and_mark_contracts() -> None:
    source = _read("/app/backend/services/notification_dispatch.py")
    assert "async def reserve_dispatch_once(" in source
    assert "async def mark_dispatch_status(" in source
    assert 'await db.notification_dispatch_log.insert_one(' in source
    assert '"dedupe_key": str(dedupe_key).strip().lower()' in source


def test_db_bootstrap_defines_notification_dispatch_unique_index() -> None:
    source = _read("/app/backend/server.py")
    assert "await db.notification_dispatch_log.create_index(\"dedupe_key\", unique=True)" in source


def test_booking_reminders_use_dispatch_ledger_reservations_before_send() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert "from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status" in source
    assert "guest_reserved = await reserve_dispatch_once(" in source
    assert "host_reserved = await reserve_dispatch_once(" in source
    assert "if not guest_reserved:" in source
    assert "if not host_reserved:" in source
    assert "await mark_dispatch_status(" in source
