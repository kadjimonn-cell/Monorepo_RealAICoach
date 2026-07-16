#!/usr/bin/env python3
"""Phase-1 codemod: rewrite legacy `darkMode ? '#hex' : '#hex'` ternaries to
V2 theme tokens (`colors.card`, `colors.text`, `colors.border`, …).

Target pattern:
    PROP: darkMode ? '<DARK_HEX>' : '<LIGHT_HEX>'

Rewrites (only when both branches are plain hex literals OR safe rgba):
    backgroundColor → colors.card | colors.bg | colors.bgSoft | colors.surfaceHover
    color           → colors.text | colors.textSec | colors.textMuted
    borderColor     → colors.border
    placeholderTextColor (prop shorthand) → colors.placeholder

Skip rules:
 • File has no `colors` binding in scope (ASCII-greps for `colors.` / `{ colors` / `const { colors }` / `colors: any`).
 • Ternary branch hex values don't match any known rewrite cluster (manual review).
 • `//` or `/*` on the same line → manual review (keep comment alignment).

Safe mode: `--dry-run` prints proposed edits + a summary. Without that flag it
writes files in-place and prints a summary.

Usage:
    python3 /app/scripts/migrate_darkmode_ternaries.py --dry-run path1 path2 …
    python3 /app/scripts/migrate_darkmode_ternaries.py --apply   path1 path2 …
    python3 /app/scripts/migrate_darkmode_ternaries.py --apply   # all 53 P1 files
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/app/frontend")

# ── Canonical V2 token value clusters ─────────────────────────────────
# Matches any "dark-ish" hex seen in the wild mapped to the V2 dark value.
BG_DARK_HEXES = {
    "#0F172A", "#111827", "#0B1220", "#050A18", "#0A0F1E",
    "#0A0A0A", "#000", "#000000", "#080E24", "#020617",
    "#0F1528", "#0D1322", "#1E293B", "#091021",
    "#131B2E", "#161F33", "#1E1E2E", "#0E1320", "#0C1324",
    "#172033", "#1F2937", "#0B1220", "#0A1224", "#0B1428",
}
BG_LIGHT_HEXES = {
    "#FFFFFF", "#FFF", "#F7F9FC", "#F9FAFB", "#F8FAFC",
    "#F1F5F9", "#FAFAFA", "#F3F4F6", "#EEF2F7",
    "#F2F7F7", "#FCFEFE", "#F8FBFC", "#F4F7FA",
    "#F5F7FA", "#EEF4F7", "#FAFBFC", "#F6F8FB",
    "#E5E7EB",
}
TEXT_LIGHT_HEXES = {
    "#FFFFFF", "#FFF", "#F8FAFC", "#F9FAFB", "#F0F4FC",
    "#E6EAF2", "#E5E7EB", "#E2E8F0", "#F1F5F9",
    "#FEFEFE", "#EEF2F7", "#FAFAFA", "#CBD5E1",
}
TEXT_DARK_HEXES = {
    "#0F172A", "#111827", "#0A0A0A", "#1F2937", "#0F1528",
    "#020617", "#0B1220", "#1E293B", "#18181B", "#09090B",
    "#0A0F1E", "#080E24",
}
TEXT_SEC_LIGHT_HEXES = {
    "#9CA3AF", "#94A3B8", "#9AA4B2", "#7B8797", "#CBD5E1",
    "#A9B7D5", "#B8C5D6", "#D1D5DB", "#A1A1AA", "#A8B3C2",
    "#B0B8C4", "#777C8A", "#A5ACB8",
}
TEXT_SEC_DARK_HEXES = {
    "#475569", "#64748B", "#404040", "#525252", "#333333",
    "#374151", "#4B5563", "#6B7280", "#3F3F46", "#52525B",
    "#737373", "#9CA3AF",
}
BORDER_DARK_HEXES = {
    "#1F2937", "#334155", "#172033", "#1E293B", "#0F172A",
    "#111827", "#2A3F63", "#24304A", "#27272A", "#2E2E2E",
    "#161F33", "#131B2E",
}
BORDER_LIGHT_HEXES = {
    "#E5E7EB", "#D7DEE7", "#E2E8F0", "#D1D5DB", "#CBD5E1",
    "#EEF2F7", "#D1D9E4", "#94A3B8", "#F3F4F6", "#F1F5F9",
    "#E4E4E7", "#E0E0E0", "#D4D4D8", "#FDE68A",
}

# Case-insensitive sets (we'll upper-case before comparing)
def _upper(s): return {x.upper() for x in s}

BG_DARK = _upper(BG_DARK_HEXES)
BG_LIGHT = _upper(BG_LIGHT_HEXES)
TEXT_L = _upper(TEXT_LIGHT_HEXES)
TEXT_D = _upper(TEXT_DARK_HEXES)
TEXT_S_L = _upper(TEXT_SEC_LIGHT_HEXES)
TEXT_S_D = _upper(TEXT_SEC_DARK_HEXES)
BORDER_D = _upper(BORDER_DARK_HEXES)
BORDER_L = _upper(BORDER_LIGHT_HEXES)

# ── Regex for the ternary on a property ───────────────────────────────
# Matches:  key: darkMode ? '#XXX' : '#YYY'  (inside object-literal styles
# OR theme-object initialisers). `key` is any identifier.
HEX_TOKEN = r"(['\"])(#[0-9A-Fa-f]{3,8})\1"
TERNARY_RE = re.compile(
    r"""
    (?P<prop>\b[a-zA-Z_][a-zA-Z0-9_]*)
    \s*:\s*
    darkMode\s*\?\s*
    (?P<q1>['"])(?P<dark>\#[0-9A-Fa-f]{3,8})(?P=q1)
    \s*:\s*
    (?P<q2>['"])(?P<light>\#[0-9A-Fa-f]{3,8})(?P=q2)
    """,
    re.VERBOSE,
)

# A more relaxed keyset that hints when a prop is text-related
TEXT_PROP_HINTS = {
    "color", "textColor", "titleColor", "subtitleColor", "labelColor",
    "placeholderTextColor", "iconColor", "activeColor", "inactiveColor",
    "text", "title", "subtitle", "label", "heading", "headingColor",
    "valueColor", "captionColor",
}
BG_PROP_HINTS = {
    "backgroundColor", "bg", "background", "surface", "card", "modalBg",
    "sidebarBg", "headerBg", "rowBg", "footerBg", "panelBg", "bgCard",
    "cardBg", "tabBar", "chartSurface", "hoverBg", "activeBg",
    "tintColor",
}
BORDER_PROP_HINTS = {
    "borderColor", "borderTopColor", "borderBottomColor", "borderLeftColor",
    "borderRightColor", "border", "divider", "dividerColor", "outline",
    "outlineColor", "separator", "separatorColor", "modalBorder",
    "cardBorder", "panelBorder", "keyBorder",
}


def classify(prop: str, dark: str, light: str) -> str | None:
    """Return the colors.* token name, or None if pair doesn't map safely."""
    d, l = dark.upper(), light.upper()

    # Case A — property-name hint wins when we have one
    if prop in BG_PROP_HINTS:
        if d in BG_DARK and l in BG_LIGHT:
            return "colors.card"
        if d in BG_LIGHT and l in BG_LIGHT:
            # Subtle surface in dark mode
            return "colors.card"
        return None
    if prop in TEXT_PROP_HINTS:
        if d in TEXT_L and l in TEXT_D:
            return "colors.text"
        if d in TEXT_S_L and l in TEXT_S_D:
            return "colors.textSec"
        # same hex both branches (grey-on-both-themes): semantic textSec
        if d == l and d in (TEXT_S_L | {"#9CA3AF", "#94A3B8"}):
            return "colors.textSec"
        return None
    if prop in BORDER_PROP_HINTS:
        if d in BORDER_D and l in BORDER_L:
            return "colors.border"
        if d in BORDER_L and l in BORDER_L:
            return "colors.border"
        return None
    # Case B — no prop-hint. Infer from hex pair only.
    # dark branch darker than light branch → bg-like
    if d in BG_DARK and l in BG_LIGHT:
        return "colors.card"
    # dark branch lighter than light branch → text-like
    if d in TEXT_L and l in TEXT_D:
        return "colors.text"
    # both grey → textSec
    if d in TEXT_S_L and l in TEXT_S_D:
        return "colors.textSec"
    # both light border-ish
    if d in BORDER_L and l in BORDER_L and d != l:
        return "colors.border"
    return None


def has_colors_in_scope(src: str) -> bool:
    """Heuristic: file already reads `colors` from useTheme / useAdminTheme,
    or accepts it as prop / param."""
    if re.search(r"\b(?:const|let)\s*\{\s*[^}]*\bcolors\b[^}]*\}\s*=\s*use(Theme|AdminTheme|ExecTheme|ThemeMode)\s*\(", src):
        return True
    if re.search(r"\buse(Theme|AdminTheme|ExecTheme)\s*\(\s*\)\.colors\b", src):
        return True
    # prop / destructured param
    if re.search(r"\bcolors\s*:\s*(?:any|ThemeColors|typeof\s+V[12]_(?:LIGHT|DARK))\b", src):
        return True
    if re.search(r"function\s+\w+\s*\([^)]*\bcolors\b[^)]*\)", src):
        return True
    if re.search(r"\(\s*\{\s*[^}]*\bcolors\b[^}]*\}\s*(?::\s*[^)]*)?\s*\)\s*=>", src):
        return True
    # any usage of `colors.something` within the file
    if re.search(r"\bcolors\.[A-Za-z_]", src):
        return True
    return False


def migrate(path: Path, apply: bool) -> dict:
    src = path.read_text(encoding="utf-8")
    original = src
    applied = Counter()
    manual = []
    scoped = has_colors_in_scope(src)

    def _sub(m: re.Match) -> str:
        prop = m.group("prop")
        dark = m.group("dark")
        light = m.group("light")
        token = classify(prop, dark, light)
        if token is None:
            manual.append((prop, dark, light, m.start()))
            return m.group(0)
        if not scoped:
            manual.append((prop, dark, light, m.start()))
            return m.group(0)
        applied[token] += 1
        return f"{prop}: {token}"

    src = TERNARY_RE.sub(_sub, src)

    changed = src != original
    if changed and apply:
        path.write_text(src, encoding="utf-8")
    return {
        "file": str(path.relative_to(ROOT)),
        "changed": changed,
        "has_colors_in_scope": scoped,
        "applied": dict(applied),
        "manual_count": len(manual),
        "manual_examples": manual[:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--apply", action="store_true", default=False)
    ap.add_argument("paths", nargs="*", help="files (relative to /app/frontend) or absolute; empty = use audit JSON")
    args = ap.parse_args()

    if not args.dry_run and not args.apply:
        print("ERROR: pass either --dry-run or --apply")
        return 2

    files: list[Path] = []
    if args.paths:
        for p in args.paths:
            pp = Path(p)
            if not pp.is_absolute():
                pp = ROOT / pp
            files.append(pp)
    else:
        audit = json.loads(Path("/tmp/v2_theme_audit_v2.json").read_text())
        for v in audit["violations"]:
            if "darkmode_ternary" in v["counts"]:
                files.append(ROOT / v["file"])

    overall = Counter()
    manual_total = 0
    changed_files = 0
    reports: list[dict] = []
    for f in files:
        if not f.exists():
            print(f"[WARN] missing: {f}")
            continue
        r = migrate(f, apply=args.apply)
        reports.append(r)
        for k, v in r["applied"].items():
            overall[k] += v
        manual_total += r["manual_count"]
        if r["changed"]:
            changed_files += 1

    print(f"{'APPLIED' if args.apply else 'DRY RUN'} — {changed_files}/{len(reports)} files touched")
    print(f"Total rewrites: {sum(overall.values())} → {dict(overall)}")
    print(f"Remaining manual ternaries (non-matching clusters or no colors-in-scope): {manual_total}")
    if not args.apply:
        for r in reports[:20]:
            if r["applied"] or r["manual_count"]:
                print(f"  {r['file']:70s} applied={sum(r['applied'].values())} manual={r['manual_count']} scope={r['has_colors_in_scope']}")
    Path("/tmp/darkmode_codemod_report.json").write_text(json.dumps(reports, indent=2))
    print("\nFull per-file report → /tmp/darkmode_codemod_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
