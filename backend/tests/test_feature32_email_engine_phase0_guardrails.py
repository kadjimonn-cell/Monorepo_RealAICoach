from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_email_policy_has_protected_reminder_family_targets() -> None:
    source = _read("/app/backend/utils/email_template_policy.py")
    assert "PROTECTED_SUBJECT_OVERRIDE_PREFIXES" in source
    assert '"reminder"' in source
    assert '"meeting_reminder"' in source
    assert '"booking_reminder"' in source


def test_email_notifications_uses_central_policy_guard_for_overrides() -> None:
    source = _read("/app/backend/utils/email_notifications.py")
    assert "from utils.email_template_policy import is_protected_subject_override_target" in source
    assert "and not is_protected_subject_override_target(normalized_email_type)" in source


def test_ab_autopromotion_blocks_protected_template_overrides() -> None:
    source = _read("/app/backend/routes/ab_testing.py")
    assert "from utils.email_template_policy import is_protected_subject_override_target" in source
    assert '"promotion_block_reason": "protected_template_subject_override_blocked"' in source
    assert '"action": "promotion_blocked_protected_template"' in source
    assert "if is_protected_subject_override_target(tpl_type):" in source


def test_ab_promotions_write_compatible_override_fields() -> None:
    source = _read("/app/backend/routes/ab_testing.py")
    assert '"email_type": tpl_type' in source
    assert '"optimized_subject": w_variant["subject_line"]' in source
    assert '"active": True' in source
