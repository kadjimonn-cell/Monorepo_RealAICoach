from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_booking_reminders_use_atomic_flag_reservation() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert "find_one_and_update(" in source
    assert 'f"{flag}_reserved_at"' in source
    assert '"status": {"$ne": "cancelled"}' in source


def test_booking_reminders_use_per_booking_tier_recipient_dedupe_keys() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert 'guest_dedupe_key = f"booking-reminder-single:{booking_id}:{guest_email_normalized}"' in source
    assert 'host_dedupe_key = f"booking-reminder-single:{booking_id}:{host_email_normalized}"' in source
    assert "dedupe_key=guest_dedupe_key" in source
    assert "dedupe_key=host_dedupe_key" in source
    assert "expected_user_id=user_id" in source
    assert "enforce_verified_primary=True" in source


def test_booking_reminders_respect_notification_email_enabled_flag() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert 'db.notification_settings.find_one({"user_id": uid}, {"_id": 0, "email_enabled": 1})' in source
    assert "if guest_email and email_enabled and guest_email_normalized:" in source
    assert "if host_email and email_enabled and host_email_normalized:" in source


def test_booking_reminders_enforce_single_email_per_booking_per_recipient() -> None:
    source = _read("/app/backend/routes/integrations.py")
    assert "recipient_single_send_guard = set()" in source
    assert '"metadata.booking_id": booking_id' in source
    assert '"email_type": {"$regex": r"^booking_reminder_"}' in source
    assert "guest_email_normalized not in recipient_single_send_guard" in source
    assert "host_email_normalized not in recipient_single_send_guard" in source


def test_meeting_reminder_template_key_collision_removed() -> None:
    source = _read("/app/backend/utils/email_templates.py")
    assert '@_register("meeting_reminder_calendar", "Meeting Reminder", "Calendar", "Upcoming meeting reminder")' in source
    assert '@_register("meeting_reminder", "Meeting Reminder", "Notifications", "Sent as a reminder before a scheduled meeting")' in source


def test_reminder_subject_overrides_blocked_for_meeting_family_templates() -> None:
    source = _read("/app/backend/utils/email_notifications.py")
    assert "from utils.email_template_policy import is_protected_subject_override_target" in source
    assert "and not is_protected_subject_override_target(normalized_email_type)" in source


def test_legacy_meeting_reminder_scheduler_no_longer_dispatches_booking_emails() -> None:
    source = _read("/app/backend/scheduler_jobs/misc.py")
    assert "canonical sender=routes.integrations.send_booking_reminders" in source
    assert "from routes.notification_engine import emit_booking_reminder" not in source
    assert "await emit_booking_reminder(" not in source
