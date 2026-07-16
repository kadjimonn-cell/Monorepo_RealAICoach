from pathlib import Path


INVITE_ACCEPT_PATH = Path('/app/frontend/app/invite-accept.tsx')
EN_LOCALE_PATH = Path('/app/frontend/src/i18n/locales/en.ts')


def test_invite_accept_uses_i18n_validation_keys() -> None:
    source = INVITE_ACCEPT_PATH.read_text(encoding='utf-8')

    assert "setError(t('validation.password_min_length'))" in source
    assert "setError(t('validation.passwords_do_not_match'))" in source
    assert 'Password must be at least 8 characters.' not in source
    assert 'Passwords do not match.' not in source


def test_en_locale_has_invite_accept_validation_keys() -> None:
    source = EN_LOCALE_PATH.read_text(encoding='utf-8')

    assert '"validation.password_min_length": "Password must be at least 8 characters."' in source
    assert '"validation.passwords_do_not_match": "Passwords do not match."' in source
