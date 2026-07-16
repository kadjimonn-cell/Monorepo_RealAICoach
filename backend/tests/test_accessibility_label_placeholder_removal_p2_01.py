from pathlib import Path
import re


FRONTEND_ROOT = Path('/app/frontend')


def test_no_generic_interactive_element_accessibility_label_remains() -> None:
    pattern = re.compile(r"accessibilityLabel\s*=\s*(['\"])Interactive element\1")

    matches = []
    for file_path in FRONTEND_ROOT.rglob('*.tsx'):
        source = file_path.read_text(encoding='utf-8', errors='ignore')
        for match in pattern.finditer(source):
            line = source.count('\n', 0, match.start()) + 1
            matches.append(f"{file_path}:{line}")

    assert not matches, "Generic accessibility labels still present:\n" + "\n".join(matches)
