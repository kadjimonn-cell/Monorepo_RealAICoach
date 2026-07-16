from pathlib import Path


SERVER_PATH = Path('/app/backend/server.py')


def test_required_secret_enforcement_function_exists_and_has_key_groups() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')

    assert 'def _enforce_required_secret_env_vars() -> None:' in source
    assert 'REQUIRED_SECRET_ENV_ENFORCE' in source
    assert '"JWT_SECRET"' in source
    assert '"RESEND_API_KEY"' in source
    assert '"PAYPAL_CLIENT_ID"' in source
    assert '"PAYPAL_SECRET"' in source
    assert '("STRIPE_SECRET_KEY", "STRIPE_API_KEY")' in source
    assert '("OPENAI_API_KEY", "EMERGENT_LLM_KEY")' in source
    assert 'REQUIRED_SECRET_ENV violation' in source


def test_startup_calls_required_secret_enforcement_after_vault_policy() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')

    startup_index = source.find('async def enforce_secret_vault_policy_startup():')
    assert startup_index != -1

    vault_call_index = source.find('_enforce_secret_vault_policy()', startup_index)
    required_call_index = source.find('_enforce_required_secret_env_vars()', startup_index)
    assert vault_call_index != -1
    assert required_call_index != -1
    assert required_call_index > vault_call_index
