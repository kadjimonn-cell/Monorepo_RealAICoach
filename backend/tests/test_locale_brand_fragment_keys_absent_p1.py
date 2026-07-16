"""
P1 · Locale Brand-Fragment Keys Absent
Regression guard: asserts that the two forbidden brand-fragment i18n keys
('autofix.precision12.real' and 'autofix.precision12.coach') are not present
in ANY locale file. These keys split the brand name "RealAICoach" into
translatable parts, risking brand-mutation (e.g. "RéelAIEntraîneur" in French).
"""
import os
import glob

LOCALES_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n', 'locales'
)

FORBIDDEN_KEYS = [
    '"autofix.precision12.real"',
    '"autofix.precision12.coach"',
]


def test_no_brand_fragment_keys_in_any_locale():
    """All 23 locale .ts files must not contain the forbidden brand-fragment keys."""
    locale_files = sorted(glob.glob(os.path.join(LOCALES_DIR, '*.ts')))
    assert locale_files, f"No locale files found at {LOCALES_DIR}"

    violations = []
    for locale_path in locale_files:
        with open(locale_path, encoding='utf-8') as fh:
            content = fh.read()
        for key in FORBIDDEN_KEYS:
            if key in content:
                violations.append(f"{os.path.basename(locale_path)}: found {key}")

    assert not violations, (
        "Brand-fragment keys found in locale files (these must be removed):\n"
        + "\n".join(violations)
    )


def test_all_23_locale_files_present():
    """Ensure the full locale set exists (no accidental file deletion)."""
    expected_locales = {
        'ar', 'de', 'en', 'es', 'fr', 'hi', 'id', 'it', 'ja',
        'ko', 'ms', 'nl', 'pl', 'pt', 'ro', 'ru', 'sv', 'sw',
        'th', 'tr', 'uk', 'vi', 'zh',
    }
    found_locales = {
        os.path.splitext(os.path.basename(f))[0]
        for f in glob.glob(os.path.join(LOCALES_DIR, '*.ts'))
    }
    missing = expected_locales - found_locales
    assert not missing, f"Missing locale files: {missing}"
