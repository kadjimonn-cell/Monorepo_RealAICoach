from pathlib import Path


DB_SOURCE_PATH = Path("/app/backend/routes/db.py")


def test_admin_override_email_no_longer_has_hardcoded_fallback() -> None:
    source = DB_SOURCE_PATH.read_text(encoding="utf-8")
    assert 'os.environ.get("ADMIN_OVERRIDE_EMAILS", "admin@realaicoach.app")' not in source
    assert 'ADMIN_OVERRIDE_EMAILS_ENV_RAW = os.environ.get("ADMIN_OVERRIDE_EMAILS")' in source


def test_preview_risk_bypass_default_email_allowlist_is_empty() -> None:
    source = DB_SOURCE_PATH.read_text(encoding="utf-8")
    assert '_RISK_PREVIEW_BYPASS_DEFAULT_EMAILS = {"admin@realaicoach.app"}' not in source
    assert "_RISK_PREVIEW_BYPASS_DEFAULT_EMAILS: set[str] = set()" in source


def test_startup_warning_present_when_admin_override_env_is_unset() -> None:
    source = DB_SOURCE_PATH.read_text(encoding="utf-8")
    assert "if ADMIN_OVERRIDE_EMAILS_ENV_RAW is None:" in source
    assert "ADMIN_OVERRIDE_EMAILS is unset" in source
