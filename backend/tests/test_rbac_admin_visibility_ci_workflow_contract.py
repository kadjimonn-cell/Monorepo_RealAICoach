from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_rbac_admin_visibility_workflow_exists_with_multibreakpoint_playwright_gate() -> None:
    source = _read("/app/.github/workflows/rbac-admin-visibility-gate.yml")

    assert "name: RBAC Admin Visibility Gate" in source
    assert "RBAC Admin Visibility E2E — Desktop Tablet Mobile" in source
    assert "e2e/admin-visibility-auth-session.spec.ts" in source
    assert "--project=desktop-chromium --project=tablet-chromium --project=mobile-chromium" in source


def test_rbac_admin_visibility_workflow_triggers_only_on_rbac_relevant_paths() -> None:
    source = _read("/app/.github/workflows/rbac-admin-visibility-gate.yml")

    required_paths = [
        "frontend/e2e/admin-visibility-auth-session.spec.ts",
        "frontend/e2e/helpers/auth.ts",
        "frontend/src/context/AccessControlContext.tsx",
        "frontend/src/components/AppShell.tsx",
        "backend/utils/access_control_engine.py",
        "backend/routes/subscription_enforcement.py",
    ]
    for path in required_paths:
        assert path in source, f"Missing RBAC gate path trigger: {path}"
