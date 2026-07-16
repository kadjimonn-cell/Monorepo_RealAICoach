from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_policy_utils_define_write_gate_and_audit_contracts() -> None:
    source = _read("/app/backend/utils/email_template_policy.py")
    assert "async def can_write_subject_override(" in source
    assert "async def audit_override_write(" in source
    assert '"reason": "protected_template_blocked"' in source
    assert '"reason": "approval_required"' in source
    assert '"reason": "approval_expired"' in source


def test_autofix_and_ab_paths_use_policy_write_gate() -> None:
    autofix = _read("/app/backend/services/email_autofix.py")
    ab = _read("/app/backend/routes/ab_testing.py")
    assert "from utils.email_template_policy import can_write_subject_override, audit_override_write" in autofix
    assert "allowed, gate = await can_write_subject_override(" in autofix
    assert "await audit_override_write(" in autofix
    assert "from utils.email_template_policy import can_write_subject_override, audit_override_write" in ab
    assert "allowed, gate = await can_write_subject_override(" in ab
    assert "promotion_blocked_policy_gate" in ab


def test_admin_policy_requires_approval_id_and_expiry_for_approvals() -> None:
    source = _read("/app/backend/routes/email_notifications.py")
    assert "approval_id is required when approved=true" in source
    assert "expires_at is required when approved=true" in source
    assert "expires_at must be in the future" in source
    assert '@router.post("/overrides/manual")' in source
    assert "allowed, gate = await can_write_subject_override(" in source
    assert "override blocked:" in source
