from pathlib import Path


def test_feature30_access_control_allowlist_for_free_users():
    source = Path('/app/frontend/src/context/AccessControlContext.tsx').read_text(encoding='utf-8')
    assert "normalizedPath.startsWith('/features/sports')" in source
    assert 'Explicit allowlist for Feature 30 (Sports v2)' in source


def test_feature30_admin_console_includes_sports_conversion_card():
    source = Path('/app/frontend/src/components/OperationsConsoleView.tsx').read_text(encoding='utf-8')
    assert "import { SportsConversionCard } from './admin/SportsConversionCard';" in source
    assert 'sports-conversion-card-wrap' in source
    assert '<SportsConversionCard colors={colors} />' in source


def test_non_admin_sidebar_filters_admin_console_hrefs_from_dom_contract():
    source = Path('/app/frontend/src/components/AppShell.tsx').read_text(encoding='utf-8')
    assert "return !target.includes('/admin-console');" in source
