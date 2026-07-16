from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_override_service_is_single_strict_write_entrypoint() -> None:
    source = _read("/app/backend/services/email_override_service.py")
    assert "async def write_subject_override(" in source
    assert "async def deactivate_subject_override(" in source
    assert "allowed, gate = await can_write_subject_override(" in source
    assert "await db.email_subject_overrides.update_one(" in source
    assert "await audit_override_write(" in source


def test_autofix_ab_admin_manual_use_override_service() -> None:
    autofix = _read("/app/backend/services/email_autofix.py")
    ab = _read("/app/backend/routes/ab_testing.py")
    admin = _read("/app/backend/routes/email_notifications.py")

    assert "from services.email_override_service import write_subject_override" in autofix
    assert "ok, gate = await write_subject_override(" in autofix

    assert "from services.email_override_service import write_subject_override" in ab
    assert "ok, gate = await write_subject_override(" in ab

    assert "from services.email_override_service import write_subject_override" in admin
    assert "ok, gate = await write_subject_override(" in admin
