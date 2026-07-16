from pathlib import Path


HTML_ENTRY_PATH = Path("/app/frontend/app/+html.tsx")


def test_early_theme_script_sets_css_variables_before_hydration() -> None:
    source = HTML_ENTRY_PATH.read_text(encoding="utf-8")

    assert "LIGHT_THEME_VARS" in source
    assert "DARK_THEME_VARS" in source
    assert "activeThemeVars" in source
    assert "root.style.setProperty(key, activeThemeVars[key]);" in source


def test_critical_app_css_vars_are_covered_in_pre_hydration_script() -> None:
    source = HTML_ENTRY_PATH.read_text(encoding="utf-8")

    required_vars = [
        "--app-bg",
        "--app-card-bg",
        "--app-text",
        "--app-text-sec",
        "--app-text-muted",
        "--app-border",
        "--app-primary",
        "--app-primary-text",
        "--app-surface",
        "--app-success",
        "--app-warning",
        "--app-error",
        "--app-info",
        "--app-surface-hover",
        "--app-card-muted",
        "--app-border-strong",
        "--app-border-bright",
        "--app-divider",
        "--app-chart-grid",
        "--app-chart-axis",
    ]

    for variable in required_vars:
        assert variable in source
