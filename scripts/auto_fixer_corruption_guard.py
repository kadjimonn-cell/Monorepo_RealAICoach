#!/usr/bin/env python3
"""auto_fixer_corruption_guard.py — black-screen prevention.

Permanent guardrail against the JSX/TSX auto-fixer corruption pattern that
caused a production black screen on Apr 25, 2026.

Root cause that triggered this guard:
  An accessibility-injection auto-fixer ran across the codebase and inserted
  `accessibilityLabel="Interactive element"` strings INSIDE arrow function
  declarations (splitting `=>` into `= … >`) and INSIDE TypeScript generic
  parameters (`useRef<TextInput>(null)` → `useRef<TextInput accessibilityLabel="…">(null)`).
  Metro's bundler aborted with `SyntaxError: Unexpected token (NN:NN)`, which
  caused `expo export --platform web` to fail, leaving no `dist/` directory.
  `serve-production.js` then fell back to proxying every request to the dev
  server (port 3001), which was OOM-looping while trying to bundle the broken
  files — net effect: black-screen with infinite spinner in the preview.

This script returns non-zero (CI fail) if ANY known corruption pattern
returns. Run it as part of pre-commit / CI / pre-export pipelines.

Usage:
  python3 scripts/auto_fixer_corruption_guard.py

Exit code:
  0 — clean
  1 — corruption detected (prints offending file:line)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path("/app/frontend")
SCAN_DIRS = [REPO / "src", REPO / "app"]
EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")

# Each entry: (regex, human-readable description). Patterns are conservative
# to avoid false positives — they match the EXACT mangling shapes produced
# by the broken auto-fixer.
PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\(\)\s*=\s+accessibilityLabel\s*="),
        "Arrow function corrupted: `() = accessibilityLabel=` "
        "(should be `() => …` with accessibilityLabel as separate prop).",
    ),
    (
        re.compile(
            r"useRef\s*<\s*[A-Za-z][A-Za-z0-9_]*\s+(?:accessibilityLabel|testID)\s*="
        ),
        "TS generic corrupted: `useRef<T accessibilityLabel=…>` "
        "(props leaked into the generic parameter).",
    ),
    (
        re.compile(
            r"useState\s*<\s*[A-Za-z][A-Za-z0-9_]*\s+(?:accessibilityLabel|testID)\s*="
        ),
        "TS generic corrupted: `useState<T accessibilityLabel=…>`.",
    ),
    (
        re.compile(r"=>\s*accessibilityLabel\s*=\s*\""),
        "Arrow body corrupted: `=> accessibilityLabel=\"…\"` injected "
        "BEFORE the function body expression.",
    ),
    (
        re.compile(r"\(\s*\)\s*\{\s*accessibilityLabel\s*="),
        "Function body corrupted: `() { accessibilityLabel=…` "
        "(prop fragment leaked into a function body).",
    ),
]


def _iter_source_files():
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in EXTENSIONS:
                yield p


def main() -> int:
    failures: list[tuple[Path, int, str, str]] = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, desc in PATTERNS:
                if pattern.search(line):
                    failures.append((path, lineno, desc, line.strip()[:200]))

    if not failures:
        print("✓ No auto-fixer corruption patterns detected "
              "across", sum(1 for _ in _iter_source_files()), "source files.")
        return 0

    print(f"✗ {len(failures)} auto-fixer corruption(s) detected — "
          "Metro bundle WILL fail and the production preview WILL black-screen:\n",
          file=sys.stderr)
    for path, lineno, desc, snippet in failures:
        rel = path.relative_to(REPO)
        print(f"  {rel}:{lineno}", file=sys.stderr)
        print(f"    why : {desc}", file=sys.stderr)
        print(f"    code: {snippet}", file=sys.stderr)
        print(file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
