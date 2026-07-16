from pathlib import Path


THEME_PATH = Path('/app/frontend/src/theme/v2.ts')
HTML_PATH = Path('/app/frontend/app/+html.tsx')


def test_dark_theme_primary_text_uses_light_neutral_token() -> None:
    source = THEME_PATH.read_text(encoding='utf-8')

    assert "primaryText: '#FFFFFF'" in source
    assert "primaryText: '#E8F5F3'" not in source
    assert "primaryText: '#041311'" not in source


def test_prehydration_theme_primary_text_matches_dark_theme_token() -> None:
    source = HTML_PATH.read_text(encoding='utf-8')

    assert "root.style.setProperty('--app-primary-text', tokens.primaryText);" in source
    assert "'--app-primary-text': '#041311'" not in source
