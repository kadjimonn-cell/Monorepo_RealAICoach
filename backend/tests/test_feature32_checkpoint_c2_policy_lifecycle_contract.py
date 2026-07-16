from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_email_notifications_exposes_revoke_endpoint_and_policy_state_lifecycle() -> None:
    source = _read("/app/backend/routes/email_notifications.py")
    assert "def _derive_policy_state(" in source
    assert '@router.post("/template-policies/override-revoke")' in source
    assert '"policy_state": "revoked"' in source
    assert '"revoke_reason is required"' in source


def test_feature32_policy_expiry_sweeper_job_exists_and_is_exported() -> None:
    policy_job = _read("/app/backend/scheduler_jobs/feature32_policy.py")
    exports = _read("/app/backend/scheduler_jobs/__init__.py")
    assert "async def scheduled_feature32_override_policy_expiry_sweeper()" in policy_job
    assert '"policy_state": "expired"' in policy_job
    assert "from scheduler_jobs.feature32_policy import" in exports
    assert "scheduled_feature32_override_policy_expiry_sweeper" in exports
