"""
P2-04 · No TODO/FIXME Comments in Production Code Paths
Regression guard: asserts that the four production files audited in P2-04 carry
zero actual TODO/FIXME comment lines.

NOTE on locale files (es.ts, it.ts, pt.ts):
  Spanish/Portuguese word "todo/todos" (= "all") and Italian "metodo" (= "method")
  contain the substring "todo", but appear ONLY inside string literals, never in
  comment lines.  This test checks comment lines only (// … or /* … */).
"""
import re
from pathlib import Path

REPO_ROOT = Path('/app')

FILES = [
    REPO_ROOT / 'frontend' / 'app' / '+html.tsx',
    REPO_ROOT / 'frontend' / 'src' / 'i18n' / 'locales' / 'es.ts',
    REPO_ROOT / 'frontend' / 'src' / 'i18n' / 'locales' / 'it.ts',
    REPO_ROOT / 'frontend' / 'src' / 'i18n' / 'locales' / 'pt.ts',
]

# Matches lines that ARE comment lines containing TODO / FIXME.
# A "comment line" starts (after optional whitespace) with // or *.
_COMMENT_TODO = re.compile(
    r'^\s*(?://|/?\*|<!--).*?(?:TODO|FIXME)',
    re.IGNORECASE,
)


def _find_comment_todos(path: Path) -> list[tuple[int, str]]:
    violations = []
    for i, raw_line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if _COMMENT_TODO.search(raw_line):
            violations.append((i, raw_line.strip()))
    return violations


def test_html_shell_no_todo_fixme():
    """+html.tsx must have no TODO/FIXME comment lines."""
    hits = _find_comment_todos(FILES[0])
    assert not hits, (
        "+html.tsx still has TODO/FIXME comment lines:\n"
        + "\n".join(f"  L{ln}: {text[:100]}" for ln, text in hits)
    )


def test_es_locale_no_todo_fixme():
    """es.ts must have no TODO/FIXME comment lines (string-literal 'todo' is fine)."""
    hits = _find_comment_todos(FILES[1])
    assert not hits, (
        "es.ts has TODO/FIXME comment lines:\n"
        + "\n".join(f"  L{ln}: {text[:100]}" for ln, text in hits)
    )


def test_it_locale_no_todo_fixme():
    """it.ts must have no TODO/FIXME comment lines."""
    hits = _find_comment_todos(FILES[2])
    assert not hits, (
        "it.ts has TODO/FIXME comment lines:\n"
        + "\n".join(f"  L{ln}: {text[:100]}" for ln, text in hits)
    )


def test_pt_locale_no_todo_fixme():
    """pt.ts must have no TODO/FIXME comment lines."""
    hits = _find_comment_todos(FILES[3])
    assert not hits, (
        "pt.ts has TODO/FIXME comment lines:\n"
        + "\n".join(f"  L{ln}: {text[:100]}" for ln, text in hits)
    )


def test_html_shell_csp_environment_detection_active():
    """+html.tsx must use isLocalHost (or !isLocalHost) for CSP gating — not a TODO stub."""
    content = (REPO_ROOT / 'frontend' / 'app' / '+html.tsx').read_text(encoding='utf-8')
    assert 'isLocalHost' in content, (
        "+html.tsx must derive shouldEnableUpgradeInsecureRequests from isLocalHost, "
        "not a hard-coded TODO stub"
    )
    assert 'shouldEnableUpgradeInsecureRequests' in content, (
        "+html.tsx must use shouldEnableUpgradeInsecureRequests to gate the CSP meta tag"
    )
    assert 'upgrade-insecure-requests' in content, (
        "+html.tsx must emit the CSP upgrade-insecure-requests tag (feature must not be removed)"
    )


def test_all_four_files_exist():
    """All four P2-04 production files must still exist (no accidental deletion)."""
    missing = [str(p) for p in FILES if not p.exists()]
    assert not missing, f"Missing production files: {missing}"
