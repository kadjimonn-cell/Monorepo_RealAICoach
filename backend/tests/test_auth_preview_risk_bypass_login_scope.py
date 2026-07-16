from pathlib import Path


AUTH_PATH = Path('/app/backend/routes/auth.py')


def test_preview_login_bypass_helper_exists_and_uses_db_guard() -> None:
    source = AUTH_PATH.read_text(encoding='utf-8')
    assert 'async def _apply_preview_login_risk_bypass_if_allowed(' in source
    assert '_apply_preview_risk_bypass_if_allowed(' in source
    assert 'preview_risk_bypass' in source


def test_preview_login_bypass_applied_to_all_auth_verification_flows() -> None:
    source = AUTH_PATH.read_text(encoding='utf-8')
    assert 'source="auth_login_password"' in source
    assert 'source="auth_otp_verify"' in source
    assert 'source="auth_2fa_verify"' in source
