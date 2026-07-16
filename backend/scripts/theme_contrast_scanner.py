#!/usr/bin/env python3
"""Text-contrast scanner/fixer for V2 theme tokens.

Flags every file where a "weak" V2 token (`.success`, `.warning`, `.indigo`,
`.orange`, `.purple`) is used as *foreground* text color. These tokens fail
WCAG AA (<4.5:1) on light surfaces. The correct replacement is the `*Text`
variant (e.g. `.successText`, `.warningText`, `.indigoText`, `.orangeText`,
`.purpleText`) which is locked to pass AA.

Detection patterns (foreground contexts):
  - `color: <obj>.<weak>`             (StyleSheet / inline style)
  - `tintColor: <obj>.<weak>`         (Image / Icon tint)
  - `color={<obj>.<weak>}`            (JSX prop on <Text>, <Ionicons>, etc.)

Usage:

    # Report only
    python backend/scripts/theme_contrast_scanner.py

    # Auto-fix (rewrites files in place)
    python backend/scripts/theme_contrast_scanner.py --fix

    # JSON summary to stdout (for CI)
    python backend/scripts/theme_contrast_scanner.py --json

Exit codes:
    0 — no violations (or --fix applied cleanly)
    1 — violations remaining

Integrates into the theme CI gate: `theme_gate.py` calls this via
`get_contrast_violations()` and enforces baseline=0.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # /app
FRONTEND_SRC_DIRS = [
    REPO_ROOT / "frontend" / "app",
    REPO_ROOT / "frontend" / "src",
]
EXCLUDE_FILES = {
    # Source of truth for tokens themselves — must keep raw values
    REPO_ROOT / "frontend" / "src" / "theme" / "v2.ts",
    REPO_ROOT / "frontend" / "src" / "theme" / "v1.ts",
    REPO_ROOT / "frontend" / "src" / "theme" / "v7.ts",
}

WEAK_TOKENS = ("success", "warning", "indigo", "orange", "purple")
TOKEN_ALT = "|".join(WEAK_TOKENS)
# Matches `<obj>.<weak>` but NOT `.<weak>Text`, `.<weak>Soft`, `.<weak>Hover`, etc.
#   group(1) = object expression (may contain dots)
#   group(2) = the weak token
TOKEN_EXPR = rf"([A-Za-z_$][\w$.]*)\.({TOKEN_ALT})(?![A-Za-z])"

# Foreground contexts
PATTERNS = [
    # StyleSheet: `color: colors.success` or `tintColor: C.warning`
    re.compile(rf"(?P<prop>\b(?:color|tintColor|placeholderTextColor|chevronColor|iconColor)\s*:\s*){TOKEN_EXPR}"),
    # JSX prop: `color={WC.success}` or `tintColor={C.warning}`
    re.compile(rf"(?P<prop>\b(?:color|tintColor|stroke|fill|placeholderTextColor|iconColor)=\{{\s*){TOKEN_EXPR}(?=\s*}})"),
]


def _should_scan(path: Path) -> bool:
    if path in EXCLUDE_FILES:
        return False
    if path.suffix not in (".ts", ".tsx", ".js", ".jsx"):
        return False
    if any(part in {"node_modules", "dist", ".expo", "build", "__tests__"} for part in path.parts):
        return False
    return True


def _walk() -> Iterable[Path]:
    for root in FRONTEND_SRC_DIRS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and _should_scan(p):
                yield p


def scan_file(path: Path) -> list[dict]:
    """Return list of violations: {file, line, col, prop, match, suggested}."""
    violations: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return violations
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Fast path — skip lines that don't reference any weak token name
        if not any(f".{tok}" in line for tok in WEAK_TOKENS):
            continue
        for pat in PATTERNS:
            for m in pat.finditer(line):
                obj = m.group(2)  # object expression
                tok = m.group(3)  # weak token
                prop = m.group("prop").strip().rstrip(":").rstrip("={").strip()
                violations.append({
                    "file": str(path.relative_to(REPO_ROOT)),
                    "line": lineno,
                    "col": m.start() + 1,
                    "prop": prop,
                    "match": m.group(0),
                    "suggested": m.group(0).replace(f"{obj}.{tok}", f"{obj}.{tok}Text"),
                    "weak_token": tok,
                })
    return violations


def fix_file(path: Path) -> tuple[int, str]:
    """Auto-swap weak-token foreground refs with their *Text variant.

    Returns (num_replacements, new_text)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0, ""
    count = 0
    new_text = text
    for pat in PATTERNS:
        def _repl(m: re.Match) -> str:
            nonlocal count
            count += 1
            obj = m.group(2)
            tok = m.group(3)
            prop = m.group("prop")
            return f"{prop}{obj}.{tok}Text"
        new_text = pat.sub(_repl, new_text)
    return count, new_text


def get_contrast_violations() -> list[dict]:
    """Entry point for CI integration (theme_gate.py)."""
    all_v: list[dict] = []
    for p in _walk():
        all_v.extend(scan_file(p))
    return all_v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="rewrite files in-place")
    ap.add_argument("--json", action="store_true", help="emit JSON summary")
    ap.add_argument("--max-print", type=int, default=50, help="max violations to print")
    args = ap.parse_args()

    files = list(_walk())
    if args.fix:
        total_fixed = 0
        changed_files: list[str] = []
        for p in files:
            n, new_text = fix_file(p)
            if n > 0:
                p.write_text(new_text, encoding="utf-8")
                total_fixed += n
                changed_files.append(str(p.relative_to(REPO_ROOT)))
        result = {
            "fixed": total_fixed,
            "files_changed": len(changed_files),
            "changed_files": changed_files,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"[contrast-fix] applied {total_fixed} replacements across {len(changed_files)} file(s)")
            for f in changed_files[:args.max_print]:
                print(f"   ✓ {f}")
        return 0

    violations = get_contrast_violations()
    files_with: set[str] = {v["file"] for v in violations}
    if args.json:
        print(json.dumps({
            "violations": len(violations),
            "files_affected": len(files_with),
            "items": violations[:args.max_print],
        }, indent=2))
    else:
        print("")
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│      Text-Contrast Scanner (WCAG AA / V2 *Text variants)    │")
        print("└─────────────────────────────────────────────────────────────┘")
        print(f"  Files scanned:     {len(files)}")
        print(f"  Files affected:    {len(files_with)}")
        print(f"  Total violations:  {len(violations)}")
        if violations:
            print("")
            print("  ── Sample violations ──")
            for v in violations[:args.max_print]:
                print(f"   ✗ {v['file']}:{v['line']}  {v['prop']}: ...{v['weak_token']} → use .{v['weak_token']}Text")
            if len(violations) > args.max_print:
                print(f"   … and {len(violations) - args.max_print} more")
            print("")
            print("  Fix with:  python backend/scripts/theme_contrast_scanner.py --fix")
        else:
            print("  ✓ No contrast violations.")
        print("")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
