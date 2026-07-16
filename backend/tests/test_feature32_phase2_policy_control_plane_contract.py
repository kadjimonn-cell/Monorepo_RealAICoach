from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_subscription_renewal_sender_uses_uno_dispatch_reservation() -> None:
    source = _read("/app/backend/routes/subscription_enforcement.py")
    assert "from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status" in source
    assert "dedupe_key = f\"renewal_reminder:{str(user_doc.get('user_id') or '')}:{days}:{email_normalized}:{renewal_date}\"" in source
    assert "reserved = await reserve_dispatch_once(" in source
    assert "if not reserved:" in source
    assert "await mark_dispatch_status(" in source


def test_phase2_template_policy_control_plane_endpoints_exist() -> None:
    source = _read("/app/backend/routes/email_notifications.py")
    assert '@router.get("/template-policies")' in source
    assert '@router.post("/template-policies/protected-sync")' in source
    assert '@router.post("/template-policies/override-approval")' in source
    assert "is_protected_subject_override_target(template_key) and approved" in source
