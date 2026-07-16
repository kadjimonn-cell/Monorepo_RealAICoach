from pathlib import Path


HTML_SHELL_PATH = Path("/app/frontend/app/+html.tsx")


def test_head_bootstrap_reads_saved_theme_before_react_mount() -> None:
    source = HTML_SHELL_PATH.read_text(encoding="utf-8")

    assert "Early theme detection: read stored preference or system preference" in source
    assert "localStorage.getItem('app_theme')" in source
    assert "root.setAttribute('data-theme-active', isDark ? 'dark' : 'light');" in source
    assert "root.setAttribute('data-theme-mode', mode);" in source


def test_head_bootstrap_sets_required_fouc_tokens() -> None:
    source = HTML_SHELL_PATH.read_text(encoding="utf-8")

    required_tokens = [
        "'--app-bg'",
        "'--app-surface'",
        "'--app-primary'",
        "'--app-primary-text'",
    ]

    for token in required_tokens:
        assert token in source, f"Missing required pre-hydration token: {token}"

    assert "var activeThemeVars = isDark ? DARK_THEME_VARS : LIGHT_THEME_VARS;" in source
    assert "Object.keys(activeThemeVars).forEach(function(key)" in source
