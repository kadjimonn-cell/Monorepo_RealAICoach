from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feature35_sync_lock_and_health_contract_present() -> None:
    source = _read("/app/backend/routes/ats_integrations.py")
    assert "SYNC_LOCK_TTL_SECONDS" in source
    assert "_acquire_sync_lock" in source
    assert "sync_already_in_progress" in source
    assert "sync_health" in source
    assert "health_score" in source


def test_feature35_credentials_encryption_and_runtime_decryption_present() -> None:
    source = _read("/app/backend/routes/ats_integrations.py")
    assert "_encrypt_credentials_for_storage" in source
    assert "_decrypt_credentials_for_runtime" in source
    assert "encrypt_field" in source
    assert "decrypt_field" in source


def test_feature35_connector_health_endpoint_present() -> None:
    source = _read("/app/backend/routes/ats_integrations.py")
    assert "@router.get(\"/{config_id}/health\")" in source
    assert "recommended_action" in source


def test_feature35_sync_schedule_guardrails_present() -> None:
    source = _read("/app/backend/routes/ats_integrations.py")
    assert "SCHEDULE_ALLOWED_HOURS" in source
    assert "invalid_sync_interval" in source
