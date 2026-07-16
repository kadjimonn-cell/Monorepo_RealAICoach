from pathlib import Path


ERROR_BOUNDARY_PATH = Path("/app/frontend/src/components/ErrorBoundary.tsx")
LANGUAGE_CONTEXT_PATH = Path("/app/frontend/src/i18n/LanguageContext.tsx")
MIDDLEWARE_PATH = Path("/app/backend/middleware.py")


def test_error_boundary_general_runtime_path_is_manual_recovery_only() -> None:
    source = ERROR_BOUNDARY_PATH.read_text(encoding="utf-8")

    assert "const RECOVERY_WINDOW_MS = 30000;" in source
    assert "setTimeout(() => window.location.reload(), 120);" not in source
    assert "error-boundary-message" in source
    assert "error-boundary-reload" in source
    assert "error-boundary-retry" in source


def test_language_provider_uses_stale_locale_during_switch() -> None:
    source = LANGUAGE_CONTEXT_PATH.read_text(encoding="utf-8")

    assert "resolvedLanguageCode" in source
    assert "fallbackLanguageCode = (localeLoading || languageSwitching || !currentRouteReady)" in source
    assert "Syncing language… showing previous content meanwhile." in source


def test_response_sanitization_is_scoped_to_api_auth_only() -> None:
    source = MIDDLEWARE_PATH.read_text(encoding="utf-8")

    assert "def _is_auth_sanitization_path(path: str) -> bool:" in source
    assert "path.startswith(\"/api/auth/\")" in source
    assert "if request.method == \"OPTIONS\" or not _is_auth_sanitization_path(path):" in source
