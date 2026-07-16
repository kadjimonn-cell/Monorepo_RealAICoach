from pathlib import Path


HTML_SHELL_PATH = Path('/app/frontend/app/+html.tsx')
CI_WORKFLOW_PATH = Path('/app/.github/workflows/ci-quality-gate.yml')
FIRST_PAINT_SPEC_PATH = Path('/app/frontend/e2e/theme-first-paint.spec.ts')


def test_html_shell_contains_pre_hydration_theme_bootstrap_and_tokens() -> None:
    source = HTML_SHELL_PATH.read_text(encoding='utf-8')

    assert 'Early theme detection: read stored preference or system preference' in source
    assert "localStorage.getItem('app_theme')" in source
    assert "root.setAttribute('data-theme-active', isDark ? 'dark' : 'light');" in source
    assert "Object.keys(activeThemeVars).forEach(function(key)" in source

    required_tokens = [
        "'--app-bg'",
        "'--app-surface'",
        "'--app-primary'",
    ]
    for token in required_tokens:
        assert token in source, f'Missing required token in +html bootstrap script: {token}'


def test_first_paint_spec_has_deterministic_readiness_gate() -> None:
    source = FIRST_PAINT_SPEC_PATH.read_text(encoding='utf-8')

    assert 'waitForFirstPaintThemeTokens' in source
    assert 'page.waitForFunction' in source
    assert "window.location.pathname !== '/auth/login'" in source
    assert 'requiredTokens' in source


def test_ci_workflow_runs_first_paint_in_dedicated_isolated_job() -> None:
    source = CI_WORKFLOW_PATH.read_text(encoding='utf-8')

    assert 'theme-first-paint-contract:' in source
    assert 'Theme First Paint Contract — Isolated' in source
    assert 'Run first-paint token contract suite' in source
    assert source.count('e2e/theme-first-paint.spec.ts') == 1
    assert '--workers=1' in source