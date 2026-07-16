from pathlib import Path


PAGE_PATH = Path('/app/frontend/app/nova-curation-hub.tsx')
EN_LOCALE_PATH = Path('/app/frontend/src/i18n/locales/en.ts')


def test_nova_curation_hub_header_uses_translation_keys() -> None:
    source = PAGE_PATH.read_text(encoding='utf-8')

    assert "tx('novaCurationHub.pageTitle', 'Nova Pinned & Favorites Hub')" in source
    assert "tx('novaCurationHub.pageSubtitle', 'Manage all saved Nova items in one place.')" in source


def test_en_locale_has_nova_curation_hub_header_keys() -> None:
    source = EN_LOCALE_PATH.read_text(encoding='utf-8')

    assert '"novaCurationHub.pageTitle": "Nova Pinned & Favorites Hub"' in source
    assert '"novaCurationHub.pageSubtitle": "Manage all saved Nova items in one place."' in source
