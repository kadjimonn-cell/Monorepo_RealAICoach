from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_themecontext_sets_switch_token_for_language_switch() -> None:
    source = _read("/app/frontend/src/context/ThemeContext.tsx")
    assert "__racI18nSwitchToken" in source
    assert "languageSwitchTokenRef" in source


def test_language_context_route_ready_not_blocked_by_language_switching() -> None:
    source = _read("/app/frontend/src/i18n/LanguageContext.tsx")
    assert "if (localeLoading) return;" in source
    assert "markRouteReady(currentRouteKey);" in source


def test_language_context_has_switch_watchdog_fail_safe() -> None:
    source = _read("/app/frontend/src/i18n/LanguageContext.tsx")
    assert "I18N_SWITCH_TIMEOUT_MS" in source
    assert "switchWatchdogRef" in source
    assert "__racI18nBackgroundOnly = false" in source


def test_en_locale_has_language_syncing_key() -> None:
    source = _read("/app/frontend/src/i18n/locales/en.ts")
    assert '"language.syncing": "Applying language…"' in source
