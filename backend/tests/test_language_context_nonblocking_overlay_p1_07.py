from pathlib import Path


SOURCE_PATH = Path('/app/frontend/src/i18n/LanguageContext.tsx')
ROOT_LAYOUT_PATH = Path('/app/frontend/app/_layout.tsx')


def test_language_context_has_sync_localstorage_locale_warm_start() -> None:
    source = SOURCE_PATH.read_text(encoding='utf-8')

    assert 'function readStoredLanguageCodeSync()' in source
    assert "window.localStorage.getItem('app_theme')" in source
    assert 'loadLocale(bootLanguageCode)' in source


def test_language_context_removes_fixed_90ms_ready_gate() -> None:
    source = SOURCE_PATH.read_text(encoding='utf-8')

    assert 'setTimeout(() => {' not in source
    assert '}, 90);' not in source
    assert 'markRouteReady(currentRouteKey);' in source


def test_language_overlay_is_non_blocking_shimmer_style() -> None:
    source = SOURCE_PATH.read_text(encoding='utf-8')

    assert 'pointerEvents="none"' in source
    assert "global-language-switch-skeleton-line-1" in source
    assert "global-language-switch-skeleton-line-2" in source
    assert "Syncing language… showing previous content meanwhile." in source


def test_language_context_keeps_previous_locale_while_new_locale_loads() -> None:
    source = SOURCE_PATH.read_text(encoding='utf-8')

    assert 'resolvedLanguageCode' in source
    assert 'isLocaleLoaded(languageCode)' in source
    assert 'fallbackLanguageCode = (localeLoading || languageSwitching || !currentRouteReady)' in source


def test_root_overlay_is_non_blocking_corner_indicator() -> None:
    source = ROOT_LAYOUT_PATH.read_text(encoding='utf-8')

    assert 'function GlobalLanguageSwitchOverlay()' in source
    assert 'pointerEvents="none"' in source
    assert 'top: 12' in source and 'right: 12' in source
    assert 'Syncing language…' in source
