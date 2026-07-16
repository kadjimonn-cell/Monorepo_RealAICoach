from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_appshell_admin_keys_not_rendered_for_non_admin() -> None:
    source = _read('/app/frontend/src/components/AppShell.tsx')
    assert "'admin-console'" in source
    assert "if (isAdmin) return true;" in source
    assert "return !target.includes('/admin-console');" in source


def test_admin_routes_use_admin_visibility_guard() -> None:
    admin_index = _read('/app/frontend/app/admin/index.tsx')
    executive = _read('/app/frontend/app/executive-dashboard.tsx')
    sub_dash = _read('/app/frontend/app/admin/subscription-dashboard.tsx')

    assert 'hasAdminConsoleVisibility' in admin_index
    assert 'hasAdminConsoleVisibility' in executive
    assert 'hasAdminConsoleVisibility' in sub_dash
    assert 'return <Redirect href="/dashboard" />;' in admin_index
    assert 'return <Redirect href="/dashboard" />;' in sub_dash
