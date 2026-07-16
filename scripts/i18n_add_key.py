#!/usr/bin/env python3
"""Add/update an i18n key in en.ts and auto-run locale seeding.

Usage:
  yarn --cwd /app/frontend i18n:add <key> "<English text>"
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

EN_FILE = Path("/app/frontend/src/i18n/locales/en.ts")
SEED_CMD = ["python3", "/app/scripts/i18n_v2_seed_locales.py"]
KEY_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")


def _read_locale(file: Path) -> dict[str, str]:
    text = file.read_text(encoding="utf-8")
    body = re.search(r"=\s*\{([\s\S]*?)\};", text)
    if not body:
        return {}
    out: dict[str, str] = {}
    for match in re.finditer(
        r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', body.group(1)
    ):
        key = match.group(1)
        value = match.group(2).replace('\\"', '"').replace("\\\\", "\\")
        out[key] = value
    return out


def _write_locale(file: Path, all_keys: dict[str, str]) -> None:
    lines = [
        "// Auto-generated locale file for en",
        "const locale: Record<string, string> = {",
    ]
    for key in sorted(all_keys.keys()):
        value = all_keys[key].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  "{key}": "{value}",')
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("};")
    lines.append("export default locale;")
    lines.append("")
    file.write_text("\n".join(lines), encoding="utf-8")


def _usage() -> int:
    print('Usage: yarn i18n:add <key> "<English text>"', file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) < 3:
        return _usage()

    key = sys.argv[1].strip()
    english_text = " ".join(sys.argv[2:]).strip()

    if not key or not english_text:
        return _usage()

    if not KEY_RE.match(key):
        print(
            "Invalid key. Use dotted/slashed lowercase keys like: section.feature.label",
            file=sys.stderr,
        )
        return 2

    if not EN_FILE.exists():
        print(f"en.ts not found at {EN_FILE}", file=sys.stderr)
        return 1

    locale = _read_locale(EN_FILE)
    previous = locale.get(key)
    locale[key] = english_text
    _write_locale(EN_FILE, locale)

    if previous is None:
        print(f"Added key: {key}")
    elif previous != english_text:
        print(f"Updated key: {key}")
    else:
        print(f"Key unchanged: {key}")

    print("Running locale seed sync...")
    result = subprocess.run(SEED_CMD, check=False)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
