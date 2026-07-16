from pathlib import Path


def _read_source() -> str:
    return Path('/app/backend/routes/ats_integrations.py').read_text(encoding='utf-8')


def test_feature35_webhook_signature_and_replay_contract_present() -> None:
    source = _read_source()
    assert 'X-Integration-Signature' in source
    assert 'X-Integration-Timestamp' in source
    assert 'X-Integration-Event-Id' in source
    assert 'webhook_replay_blocked' in source
    assert 'signature_verified' in source


def test_feature35_test_mode_seed_cleanup_policy_contract_present() -> None:
    source = _read_source()
    assert 'TEST_MODE_SEED_RETENTION_HOURS' in source
    assert '_cleanup_test_mode_seed_connectors' in source
    assert '_maybe_run_seed_cleanup_from_scheduler' in source
    assert '@router.get("/admin/test-mode-seed-policy")' in source
    assert '@router.post("/admin/test-mode-seed-cleanup/run")' in source
