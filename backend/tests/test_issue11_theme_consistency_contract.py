from pathlib import Path


V2_THEME_PATH = Path('/app/frontend/src/theme/v2.ts')
THEME_CONTEXT_PATH = Path('/app/frontend/src/context/ThemeContext.tsx')
HTML_SHELL_PATH = Path('/app/frontend/app/+html.tsx')


def test_issue11_v2_dark_primary_and_button_text_are_wcag_safe_white() -> None:
    source = V2_THEME_PATH.read_text(encoding='utf-8')

    assert "primaryText: '#FFFFFF'" in source
    assert "buttonText: '#FFFFFF'" in source
    assert "primaryText: '#0B1220'" not in source
    assert "buttonText: '#0B1220'" not in source


def test_issue11_theme_context_uses_neutral_pre_mount_fallback() -> None:
    source = THEME_CONTEXT_PATH.read_text(encoding='utf-8')

    assert 'const THEME_NEUTRAL_FALLBACK_COLORS = {' in source
    assert '...V1_LIGHT,' in source
    assert 'darkMode: false,' in source
    assert "themeMode: 'system' as ThemeMode," in source


def test_issue11_head_has_prehydrate_theme_script() -> None:
    source = HTML_SHELL_PATH.read_text(encoding='utf-8')

    assert 'id="rac-prehydrate-theme"' in source
    assert "localStorage.getItem(candidates[i])" in source
    assert "root.setAttribute('data-theme-active'" in source
    assert "root.style.setProperty('--app-primary-text', tokens.primaryText);" in source
